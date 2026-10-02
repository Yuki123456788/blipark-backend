"""Source-neutral orchestration for observable parking ingestion."""

from collections.abc import Callable, Iterable
from dataclasses import asdict, dataclass, field
from datetime import datetime
from typing import Any, Protocol
from uuid import UUID

from django.utils import timezone
from pydantic import BaseModel, ValidationError

from parking.exceptions import IngestionClientError, IngestionResponseError
from parking.models import (
    SourceDataset,
    SourceProvider,
    SyncDatasetResult,
    SyncIssue,
    SyncIssueStage,
    SyncRun,
    SyncStatus,
    SyncTrigger,
)
from parking.normalization import NormalizedRecord
from parking.repositories import (
    ParkingPersistenceError,
    ParkingRepository,
    UpsertDisposition,
    UpsertResult,
)


@dataclass(frozen=True, slots=True)
class DatasetProcessor:
    dataset: Any
    source_dataset: SourceDataset
    record_model: type[BaseModel]
    mapper: Callable[[Any, Any], list[NormalizedRecord]]
    source_id_fields: tuple[str, ...]
    dependencies: tuple[Any, ...] = ()
    mapping_error_types: tuple[type[Exception], ...] = (ValueError,)
    authority_by_city: dict[str, str] = field(default_factory=dict)


@dataclass(slots=True)
class SyncCounters:
    pages_fetched: int = 0
    fetched: int = 0
    valid: int = 0
    invalid: int = 0
    mapped: int = 0
    inserted: int = 0
    updated: int = 0
    unchanged: int = 0
    failed: int = 0


@dataclass(frozen=True, slots=True)
class IssueRecord:
    stage: SyncIssueStage
    code: str
    summary: str
    source_id: str = ""
    page_offset: int | None = None
    record_index: int | None = None
    field_paths: tuple[str, ...] = ()


@dataclass(slots=True)
class DatasetSummary:
    dataset: Any
    status: SyncStatus
    counters: SyncCounters = field(default_factory=SyncCounters)
    source_updated_at: datetime | None = None
    source_version_id: int | None = None
    error_summary: str = ""


@dataclass(frozen=True, slots=True)
class SyncSummary:
    run_id: UUID
    status: SyncStatus
    datasets: tuple[DatasetSummary, ...]


class SyncRecorder(Protocol):
    def start_run(self, *, city: str, started_at: datetime) -> UUID: ...

    def start_dataset(self, run_id: UUID, processor: DatasetProcessor, *, started_at: datetime): ...

    def record_issue(self, dataset_result_id, issue: IssueRecord): ...

    def finish_dataset(
        self,
        dataset_result_id,
        summary: DatasetSummary,
        *,
        finished_at: datetime,
    ): ...

    def finish_run(
        self,
        run_id: UUID,
        *,
        status: SyncStatus,
        authority_code: str,
        error_summary: str,
        finished_at: datetime,
    ): ...


class DjangoSyncRecorder:
    def start_run(self, *, city: str, started_at: datetime) -> UUID:
        run = SyncRun.objects.create(
            source=SourceProvider.TDX,
            city=city,
            trigger=SyncTrigger.MANUAL_CLI,
            started_at=started_at,
        )
        return run.pk

    def start_dataset(self, run_id: UUID, processor: DatasetProcessor, *, started_at: datetime):
        result = SyncDatasetResult.objects.create(
            run_id=run_id,
            dataset=processor.source_dataset,
            started_at=started_at,
        )
        return result.pk

    def record_issue(self, dataset_result_id, issue: IssueRecord):
        SyncIssue.objects.create(
            dataset_result_id=dataset_result_id,
            stage=issue.stage,
            code=issue.code,
            source_id=issue.source_id,
            page_offset=issue.page_offset,
            record_index=issue.record_index,
            field_paths=list(issue.field_paths),
            summary=issue.summary[:2000],
        )

    def finish_dataset(
        self,
        dataset_result_id,
        summary: DatasetSummary,
        *,
        finished_at: datetime,
    ):
        SyncDatasetResult.objects.filter(pk=dataset_result_id).update(
            status=summary.status,
            finished_at=finished_at,
            source_updated_at=summary.source_updated_at,
            source_version_id=summary.source_version_id,
            error_summary=summary.error_summary[:2000],
            **asdict(summary.counters),
        )

    def finish_run(
        self,
        run_id: UUID,
        *,
        status: SyncStatus,
        authority_code: str,
        error_summary: str,
        finished_at: datetime,
    ):
        SyncRun.objects.filter(pk=run_id).update(
            status=status,
            authority_code=authority_code,
            error_summary=error_summary[:2000],
            finished_at=finished_at,
        )


class ParkingSyncService:
    def __init__(
        self,
        *,
        client: Any,
        processors: Iterable[DatasetProcessor],
        repository: ParkingRepository | None = None,
        recorder: SyncRecorder | None = None,
        clock: Callable[[], datetime] = timezone.now,
        max_issues_per_dataset: int = 1000,
    ):
        self.client = client
        self.processors = tuple(processors)
        self.repository = repository or ParkingRepository()
        self.recorder = recorder or DjangoSyncRecorder()
        self.clock = clock
        self.max_issues_per_dataset = max_issues_per_dataset

    def sync(
        self,
        *,
        city: str = "Tainan",
        datasets: Iterable[Any] | None = None,
    ) -> SyncSummary:
        selected = (
            {processor.dataset for processor in self.processors}
            if datasets is None
            else set(datasets)
        )
        started_at = self.clock()
        run_id = self.recorder.start_run(city=city, started_at=started_at)
        summaries: list[DatasetSummary] = []
        status_by_dataset: dict[Any, SyncStatus] = {}
        authority_code = ""

        for processor in self.processors:
            if processor.dataset not in selected:
                continue
            dataset_result_id = self.recorder.start_dataset(
                run_id,
                processor,
                started_at=self.clock(),
            )
            blocking_dependencies = [
                dependency.value
                for dependency in processor.dependencies
                if status_by_dataset.get(dependency) == SyncStatus.FAILED
            ]
            if blocking_dependencies:
                summary = DatasetSummary(
                    dataset=processor.dataset,
                    status=SyncStatus.FAILED,
                    error_summary=f"Blocked by failed datasets: {', '.join(blocking_dependencies)}",
                )
                self.recorder.record_issue(
                    dataset_result_id,
                    IssueRecord(
                        stage=SyncIssueStage.FETCH,
                        code="dependency_failed",
                        summary=summary.error_summary,
                    ),
                )
            else:
                summary, observed_authority = self._sync_dataset(
                    processor,
                    city=city,
                    dataset_result_id=dataset_result_id,
                    seen_at=started_at,
                )
                if observed_authority:
                    if authority_code and authority_code != observed_authority:
                        summary.status = SyncStatus.FAILED
                        summary.error_summary = (
                            f"Authority changed from {authority_code} to {observed_authority}"
                        )
                    else:
                        authority_code = observed_authority

            self.recorder.finish_dataset(
                dataset_result_id,
                summary,
                finished_at=self.clock(),
            )
            summaries.append(summary)
            status_by_dataset[processor.dataset] = summary.status

        run_status = self._run_status(summaries)
        errors = "; ".join(
            f"{summary.dataset.value}: {summary.error_summary}"
            for summary in summaries
            if summary.error_summary
        )
        self.recorder.finish_run(
            run_id,
            status=run_status,
            authority_code=authority_code,
            error_summary=errors,
            finished_at=self.clock(),
        )
        return SyncSummary(run_id=run_id, status=run_status, datasets=tuple(summaries))

    def _sync_dataset(
        self,
        processor: DatasetProcessor,
        *,
        city: str,
        dataset_result_id,
        seen_at: datetime,
    ) -> tuple[DatasetSummary, str]:
        summary = DatasetSummary(dataset=processor.dataset, status=SyncStatus.SUCCEEDED)
        issue_count = 0
        authority_code = ""
        try:
            for page in self.client.iter_pages(processor.dataset, city=city):
                summary.counters.pages_fetched += 1
                summary.counters.fetched += len(page.records)
                expected_authority = processor.authority_by_city.get(city)
                if expected_authority and page.metadata.authority_code != expected_authority:
                    raise IngestionResponseError(
                        f"{processor.dataset.value} returned authority "
                        f"{page.metadata.authority_code} for {city}, expected {expected_authority}"
                    )
                authority_code = authority_code or page.metadata.authority_code
                if page.metadata.authority_code != authority_code:
                    raise IngestionResponseError(
                        f"{processor.dataset.value} authority changed during pagination"
                    )
                summary.source_updated_at = page.metadata.source_updated_at
                summary.source_version_id = page.metadata.version_id
                for record_index, raw_record in enumerate(page.records):
                    source_id = self._source_id(raw_record, processor.source_id_fields)
                    try:
                        dto = processor.record_model.model_validate(raw_record)
                    except ValidationError as error:
                        summary.counters.invalid += 1
                        issue = self._validation_issue(
                            error,
                            source_id=source_id,
                            page=page,
                            record_index=record_index,
                        )
                        issue_count = self._record_issue(
                            dataset_result_id,
                            issue,
                            issue_count,
                        )
                        continue
                    summary.counters.valid += 1

                    try:
                        mapped_records = processor.mapper(dto, page.metadata)
                    except processor.mapping_error_types as error:
                        summary.counters.failed += 1
                        issue_count = self._record_issue(
                            dataset_result_id,
                            IssueRecord(
                                stage=SyncIssueStage.MAPPING,
                                code="mapping_error",
                                summary=str(error),
                                source_id=source_id,
                                page_offset=page.offset,
                                record_index=record_index,
                            ),
                            issue_count,
                        )
                        continue

                    summary.counters.mapped += len(mapped_records)
                    for mapped_record in mapped_records:
                        try:
                            outcome = self.repository.upsert(mapped_record, seen_at=seen_at)
                        except ParkingPersistenceError as error:
                            summary.counters.failed += 1
                            issue_count = self._record_issue(
                                dataset_result_id,
                                IssueRecord(
                                    stage=SyncIssueStage.PERSISTENCE,
                                    code=type(error).__name__,
                                    summary=str(error),
                                    source_id=mapped_record.identity.source_id,
                                    page_offset=page.offset,
                                    record_index=record_index,
                                ),
                                issue_count,
                            )
                            continue
                        except Exception as error:
                            summary.counters.failed += 1
                            issue_count = self._record_issue(
                                dataset_result_id,
                                IssueRecord(
                                    stage=SyncIssueStage.PERSISTENCE,
                                    code=type(error).__name__,
                                    summary=f"Persistence failed: {type(error).__name__}",
                                    source_id=mapped_record.identity.source_id,
                                    page_offset=page.offset,
                                    record_index=record_index,
                                ),
                                issue_count,
                            )
                            continue
                        self._count_upsert(summary.counters, outcome)
        except IngestionClientError as error:
            summary.status = SyncStatus.FAILED
            summary.error_summary = str(error)
            self._record_issue(
                dataset_result_id,
                IssueRecord(
                    stage=SyncIssueStage.FETCH,
                    code=type(error).__name__,
                    summary=str(error),
                ),
                issue_count,
            )
            return summary, authority_code

        if summary.counters.invalid or summary.counters.failed:
            summary.status = SyncStatus.PARTIAL
            summary.error_summary = (
                f"{summary.counters.invalid} invalid source records; "
                f"{summary.counters.failed} mapped entities failed"
            )
        return summary, authority_code

    def _record_issue(self, dataset_result_id, issue: IssueRecord, issue_count: int) -> int:
        if issue_count < self.max_issues_per_dataset:
            self.recorder.record_issue(dataset_result_id, issue)
        return issue_count + 1

    @staticmethod
    def _validation_issue(
        error: ValidationError,
        *,
        source_id: str,
        page: Any,
        record_index: int,
    ) -> IssueRecord:
        details = error.errors(include_url=False, include_context=False, include_input=False)
        paths = tuple(".".join(str(part) for part in detail["loc"]) for detail in details)
        summary = "; ".join(
            f"{path or '<record>'}: {detail['msg']}"
            for path, detail in zip(paths, details, strict=True)
        )
        return IssueRecord(
            stage=SyncIssueStage.VALIDATION,
            code="schema_validation",
            summary=summary,
            source_id=source_id,
            page_offset=page.offset,
            record_index=record_index,
            field_paths=paths,
        )

    @staticmethod
    def _source_id(raw_record: dict[str, Any], fields: tuple[str, ...]) -> str:
        return next(
            (str(raw_record[field]) for field in fields if raw_record.get(field) is not None),
            "",
        )

    @staticmethod
    def _count_upsert(counters: SyncCounters, outcome: UpsertResult):
        if outcome.disposition == UpsertDisposition.INSERTED:
            counters.inserted += 1
        elif outcome.disposition == UpsertDisposition.UPDATED:
            counters.updated += 1
        else:
            counters.unchanged += 1

    @staticmethod
    def _run_status(summaries: list[DatasetSummary]) -> SyncStatus:
        if summaries and all(summary.status == SyncStatus.SUCCEEDED for summary in summaries):
            return SyncStatus.SUCCEEDED
        if summaries and all(summary.status == SyncStatus.FAILED for summary in summaries):
            return SyncStatus.FAILED
        return SyncStatus.PARTIAL
