from django.core.management.base import BaseCommand, CommandError

from integrations.tdx.client import TDXClientError, TDXDataset
from integrations.tdx.runner import run_tdx_sync
from parking.models import SourceProvider, SyncStatus
from parking.sync_lock import SyncAlreadyRunningError, single_sync_run


class Command(BaseCommand):
    help = "Synchronize validated TDX static parking data into the Blipark database."

    def add_arguments(self, parser):
        parser.add_argument("--city", choices=("Tainan",), default="Tainan")
        parser.add_argument(
            "--dataset",
            action="append",
            choices=tuple(dataset.value for dataset in TDXDataset),
            dest="datasets",
            help="Sync only this dataset; repeat the option to select more than one.",
        )

    def handle(self, *args, **options):
        datasets = (
            [TDXDataset(value) for value in options["datasets"]] if options["datasets"] else None
        )
        try:
            with single_sync_run(source=SourceProvider.TDX, city=options["city"]):
                summary = run_tdx_sync(
                    city=options["city"],
                    datasets=datasets,
                )
        except (TDXClientError, SyncAlreadyRunningError) as error:
            raise CommandError(str(error)) from error

        for dataset in summary.datasets:
            counters = dataset.counters
            self.stdout.write(
                f"{dataset.dataset.value}: {dataset.status} "
                f"fetched={counters.fetched} valid={counters.valid} invalid={counters.invalid} "
                f"inserted={counters.inserted} updated={counters.updated} "
                f"unchanged={counters.unchanged} failed={counters.failed}"
            )
        self.stdout.write(f"SyncRun {summary.run_id}: {summary.status}")

        if summary.status != SyncStatus.SUCCEEDED:
            raise CommandError(f"TDX sync completed with status {summary.status}")
