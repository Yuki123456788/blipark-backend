from contextlib import nullcontext
from unittest.mock import patch

import pytest
from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import override_settings


@override_settings(TDX_CLIENT_ID="", TDX_CLIENT_SECRET="")
@patch("parking.management.commands.sync_tdx.single_sync_run", return_value=nullcontext())
def test_sync_command_fails_closed_without_credentials(_sync_lock):
    with pytest.raises(CommandError, match="credentials are required"):
        call_command("sync_tdx")
