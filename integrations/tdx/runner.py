"""Shared construction and execution of a TDX parking sync."""

from collections.abc import Iterable

from django.conf import settings

from parking.models import SyncTrigger
from parking.services.sync import ParkingSyncService, SyncSummary

from .client import TDXClient, TDXDataset
from .pipeline import TDX_PROCESSORS


def run_tdx_sync(
    *,
    city: str = "Tainan",
    datasets: Iterable[TDXDataset] | None = None,
    trigger: SyncTrigger = SyncTrigger.MANUAL_CLI,
) -> SyncSummary:
    with TDXClient(
        client_id=settings.TDX_CLIENT_ID,
        client_secret=settings.TDX_CLIENT_SECRET,
        base_url=settings.TDX_BASE_URL,
        token_url=settings.TDX_TOKEN_URL,
        timeout_seconds=settings.TDX_TIMEOUT_SECONDS,
        page_size=settings.TDX_PAGE_SIZE,
        max_attempts=settings.TDX_MAX_ATTEMPTS,
    ) as client:
        return ParkingSyncService(client=client, processors=TDX_PROCESSORS).sync(
            city=city,
            datasets=datasets,
            trigger=trigger,
        )
