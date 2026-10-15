"""Cross-process exclusion for manually triggered sync runs."""

import hashlib
from contextlib import contextmanager

from django.db import connection


class SyncAlreadyRunningError(RuntimeError):
    pass


def _lock_key(source: str, city: str) -> int:
    digest = hashlib.blake2b(f"{source}:{city}".encode(), digest_size=8).digest()
    return int.from_bytes(digest, byteorder="big", signed=True)


@contextmanager
def single_sync_run(*, source: str, city: str):
    """Hold a PostgreSQL session advisory lock for the duration of a sync."""

    if connection.vendor != "postgresql":
        raise RuntimeError("Sync locking requires PostgreSQL")

    key = _lock_key(source, city)
    with connection.cursor() as cursor:
        cursor.execute("SELECT pg_try_advisory_lock(%s)", [key])
        acquired = cursor.fetchone()[0]
    if not acquired:
        raise SyncAlreadyRunningError(f"A {source} sync for {city} is already running")

    try:
        yield
    finally:
        with connection.cursor() as cursor:
            cursor.execute("SELECT pg_advisory_unlock(%s)", [key])
