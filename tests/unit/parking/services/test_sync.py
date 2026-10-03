import json
from copy import deepcopy
from pathlib import Path
from uuid import UUID

from integrations.tdx.client import TDXDataset, TDXPage, TDXRequestError
from integrations.tdx.pipeline import TDX_PROCESSORS
from integrations.tdx.schemas import (
    TDXCarParkResponse,
    TDXOffStreetSpotResponse,
    TDXParkingEntranceExitResponse,
    TDXParkingSegmentResponse,
)
from parking.models import SyncIssueStage, SyncStatus, SyncTrigger
from parking.repositories import MissingParentError, UpsertDisposition, UpsertResult
from parking.services.sync import ParkingSyncService

FIXTURE_DIR = Path(__file__).parents[3] / "fixtures" / "tdx"
RUN_ID = UUID("00000000-0000-0000-0000-000000000001")
ENTITY_ID = UUID("00000000-0000-0000-0000-000000000002")


def fixture_payload(filename):
    return json.loads((FIXTURE_DIR / filename).read_text())


def fixture_page(dataset, filename, response_model, records_key):
    payload = fixture_payload(filename)
    response = response_model.model_validate(payload)
    return TDXPage(dataset=dataset, metadata=response, records=payload[records_key], offset=0)


class FakeClient:
    def __init__(self, pages_by_dataset):
        self.pages_by_dataset = pages_by_dataset
        self.calls = []

    def iter_pages(self, dataset, *, city):
        self.calls.append((dataset, city))
        result = self.pages_by_dataset[dataset]
        if isinstance(result, Exception):
            raise result
        yield from result


class FakeRepository:
    def __init__(self, *, error=None):
        self.error = error
        self.records = []

    def upsert(self, record, *, seen_at):
        self.records.append((record, seen_at))
        if self.error:
            raise self.error
        return UpsertResult(ENTITY_ID, UpsertDisposition.INSERTED)


class FakeRecorder:
    def __init__(self):
        self.started = []
        self.issues = []
        self.dataset_finishes = []
        self.run_finish = None

    def start_run(self, *, city, trigger, started_at):
        self.started.append(("run", city, trigger, started_at))
        return RUN_ID

    def start_dataset(self, run_id, processor, *, started_at):
        result_id = len(self.started)
        self.started.append(("dataset", processor.dataset, started_at))
        return result_id

    def record_issue(self, dataset_result_id, issue):
        self.issues.append((dataset_result_id, issue))

    def finish_dataset(self, dataset_result_id, summary, *, finished_at):
        self.dataset_finishes.append((dataset_result_id, summary, finished_at))

    def finish_run(self, run_id, **values):
        self.run_finish = (run_id, values)


def test_service_counts_source_records_and_flattened_domain_entities():
    car_page = fixture_page(
        TDXDataset.CAR_PARKS,
        "car_parks.json",
        TDXCarParkResponse,
        "CarParks",
    )
    spot_page = fixture_page(
        TDXDataset.OFF_STREET_SPOTS,
        "off_street_parking_spots.json",
        TDXOffStreetSpotResponse,
        "ParkingSpots",
    )
    client = FakeClient(
        {
            TDXDataset.CAR_PARKS: [car_page],
            TDXDataset.OFF_STREET_SPOTS: [spot_page],
        }
    )
    repository = FakeRepository()
    recorder = FakeRecorder()

    summary = ParkingSyncService(
        client=client,
        processors=TDX_PROCESSORS,
        repository=repository,
        recorder=recorder,
    ).sync(datasets=[TDXDataset.CAR_PARKS, TDXDataset.OFF_STREET_SPOTS])

    lot, spots = summary.datasets
    assert summary.status == SyncStatus.SUCCEEDED
    assert (lot.counters.fetched, lot.counters.mapped, lot.counters.inserted) == (1, 1, 1)
    assert (spots.counters.fetched, spots.counters.mapped, spots.counters.inserted) == (1, 3, 3)
    assert len(repository.records) == 4


def test_service_records_the_selected_trigger():
    car_page = fixture_page(
        TDXDataset.CAR_PARKS,
        "car_parks.json",
        TDXCarParkResponse,
        "CarParks",
    )
    recorder = FakeRecorder()

    ParkingSyncService(
        client=FakeClient({TDXDataset.CAR_PARKS: [car_page]}),
        processors=TDX_PROCESSORS,
        repository=FakeRepository(),
        recorder=recorder,
    ).sync(datasets=[TDXDataset.CAR_PARKS], trigger=SyncTrigger.MANUAL_ADMIN)

    assert recorder.started[0][2] == SyncTrigger.MANUAL_ADMIN


def test_service_continues_after_entity_validation_failure_without_raw_payload_issue():
    payload = fixture_payload("car_parks.json")
    invalid = deepcopy(payload["CarParks"][0])
    invalid["CarParkID"] = " "
    response = TDXCarParkResponse.model_validate(payload)
    page = TDXPage(
        dataset=TDXDataset.CAR_PARKS,
        metadata=response,
        records=[invalid, payload["CarParks"][0]],
        offset=0,
    )
    recorder = FakeRecorder()

    summary = ParkingSyncService(
        client=FakeClient({TDXDataset.CAR_PARKS: [page]}),
        processors=TDX_PROCESSORS,
        repository=FakeRepository(),
        recorder=recorder,
    ).sync(datasets=[TDXDataset.CAR_PARKS])

    dataset = summary.datasets[0]
    assert summary.status == SyncStatus.PARTIAL
    assert (dataset.counters.fetched, dataset.counters.valid, dataset.counters.invalid) == (2, 1, 1)
    issue = recorder.issues[0][1]
    assert issue.stage == SyncIssueStage.VALIDATION
    assert issue.field_paths == ("CarParkID",)
    assert "萬昌街" not in issue.summary


def test_failed_parent_dataset_blocks_dependents_but_not_independent_datasets():
    segment_page = fixture_page(
        TDXDataset.PARKING_SEGMENTS,
        "parking_segments.json",
        TDXParkingSegmentResponse,
        "ParkingSegments",
    )
    client = FakeClient(
        {
            TDXDataset.CAR_PARKS: TDXRequestError("upstream unavailable", status_code=503),
            TDXDataset.PARKING_ENTRANCE_EXITS: [],
            TDXDataset.PARKING_SEGMENTS: [segment_page],
        }
    )
    recorder = FakeRecorder()

    summary = ParkingSyncService(
        client=client,
        processors=TDX_PROCESSORS,
        repository=FakeRepository(),
        recorder=recorder,
    ).sync(
        datasets=[
            TDXDataset.CAR_PARKS,
            TDXDataset.PARKING_ENTRANCE_EXITS,
            TDXDataset.PARKING_SEGMENTS,
        ]
    )

    assert summary.status == SyncStatus.PARTIAL
    assert [dataset.status for dataset in summary.datasets] == [
        SyncStatus.FAILED,
        SyncStatus.FAILED,
        SyncStatus.SUCCEEDED,
    ]
    assert (TDXDataset.PARKING_ENTRANCE_EXITS, "Tainan") not in client.calls
    assert any(issue.code == "dependency_failed" for _, issue in recorder.issues)


def test_persistence_failure_isolated_to_each_mapped_entity():
    spot_page = fixture_page(
        TDXDataset.OFF_STREET_SPOTS,
        "off_street_parking_spots.json",
        TDXOffStreetSpotResponse,
        "ParkingSpots",
    )
    recorder = FakeRecorder()

    summary = ParkingSyncService(
        client=FakeClient({TDXDataset.OFF_STREET_SPOTS: [spot_page]}),
        processors=TDX_PROCESSORS,
        repository=FakeRepository(error=MissingParentError("parent missing")),
        recorder=recorder,
    ).sync(datasets=[TDXDataset.OFF_STREET_SPOTS])

    dataset = summary.datasets[0]
    assert dataset.status == SyncStatus.PARTIAL
    assert dataset.counters.mapped == 3
    assert dataset.counters.failed == 3
    assert len(recorder.issues) == 3


def test_service_rejects_wrong_authority_before_mapping_records():
    car_page = fixture_page(
        TDXDataset.CAR_PARKS,
        "car_parks.json",
        TDXCarParkResponse,
        "CarParks",
    )
    car_page.metadata.authority_code = "KHH"
    repository = FakeRepository()

    summary = ParkingSyncService(
        client=FakeClient({TDXDataset.CAR_PARKS: [car_page]}),
        processors=TDX_PROCESSORS,
        repository=repository,
        recorder=FakeRecorder(),
    ).sync(datasets=[TDXDataset.CAR_PARKS])

    assert summary.status == SyncStatus.FAILED
    assert "expected TNN" in summary.datasets[0].error_summary
    assert repository.records == []


def test_issue_persistence_is_capped_while_counters_remain_complete():
    payload = fixture_payload("parking_entrance_exits.json")
    response = TDXParkingEntranceExitResponse.model_validate(payload)
    invalid_records = [{"CarParkID": str(index)} for index in range(3)]
    page = TDXPage(
        dataset=TDXDataset.PARKING_ENTRANCE_EXITS,
        metadata=response,
        records=invalid_records,
        offset=0,
    )
    recorder = FakeRecorder()

    summary = ParkingSyncService(
        client=FakeClient({TDXDataset.PARKING_ENTRANCE_EXITS: [page]}),
        processors=TDX_PROCESSORS,
        repository=FakeRepository(),
        recorder=recorder,
        max_issues_per_dataset=1,
    ).sync(datasets=[TDXDataset.PARKING_ENTRANCE_EXITS])

    assert summary.datasets[0].counters.invalid == 3
    assert len(recorder.issues) == 1
