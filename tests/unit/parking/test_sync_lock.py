from unittest.mock import Mock, patch

import pytest

from parking.sync_lock import SyncAlreadyRunningError, single_sync_run


def cursor_context(*fetch_results):
    cursor = Mock()
    cursor.fetchone.side_effect = fetch_results
    context = Mock()
    context.__enter__ = Mock(return_value=cursor)
    context.__exit__ = Mock(return_value=False)
    return context, cursor


@patch("parking.sync_lock.connection")
def test_single_sync_run_holds_and_releases_postgres_advisory_lock(connection):
    acquire_context, acquire_cursor = cursor_context((True,))
    release_context, release_cursor = cursor_context()
    connection.vendor = "postgresql"
    connection.cursor.side_effect = [acquire_context, release_context]

    with single_sync_run(source="tdx", city="Tainan"):
        pass

    assert acquire_cursor.execute.call_args.args[0] == "SELECT pg_try_advisory_lock(%s)"
    assert release_cursor.execute.call_args.args[0] == "SELECT pg_advisory_unlock(%s)"
    assert acquire_cursor.execute.call_args.args[1] == release_cursor.execute.call_args.args[1]


@patch("parking.sync_lock.connection")
def test_single_sync_run_rejects_a_duplicate_without_unlocking(connection):
    acquire_context, acquire_cursor = cursor_context((False,))
    connection.vendor = "postgresql"
    connection.cursor.return_value = acquire_context

    with pytest.raises(SyncAlreadyRunningError, match="already running"):
        with single_sync_run(source="tdx", city="Tainan"):
            pass

    assert connection.cursor.call_count == 1
    assert acquire_cursor.execute.call_args.args[0] == "SELECT pg_try_advisory_lock(%s)"
