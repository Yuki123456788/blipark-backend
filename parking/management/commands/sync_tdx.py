from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from integrations.tdx.client import TDXClient, TDXClientError, TDXDataset
from parking.models import SyncStatus
from parking.services.sync import ParkingSyncService


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
            with TDXClient(
                client_id=settings.TDX_CLIENT_ID,
                client_secret=settings.TDX_CLIENT_SECRET,
                base_url=settings.TDX_BASE_URL,
                token_url=settings.TDX_TOKEN_URL,
                timeout_seconds=settings.TDX_TIMEOUT_SECONDS,
                page_size=settings.TDX_PAGE_SIZE,
                max_attempts=settings.TDX_MAX_ATTEMPTS,
            ) as client:
                summary = ParkingSyncService(client=client).sync(
                    city=options["city"],
                    datasets=datasets,
                )
        except TDXClientError as error:
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
