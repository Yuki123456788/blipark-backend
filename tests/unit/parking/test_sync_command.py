import pytest
from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import override_settings


@override_settings(TDX_CLIENT_ID="", TDX_CLIENT_SECRET="")
def test_sync_command_fails_closed_without_credentials():
    with pytest.raises(CommandError, match="credentials are required"):
        call_command("sync_tdx")
