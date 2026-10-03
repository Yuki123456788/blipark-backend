import os
from contextlib import nullcontext
from types import SimpleNamespace
from unittest.mock import patch
from uuid import uuid4

import pytest
from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.gis.geos import Point
from django.test import override_settings
from django.urls import reverse
from django.utils import timezone

from parking.admin_inspection import build_data_inspection_context
from parking.models import (
    AccessKind,
    EntityKind,
    IdentifierKind,
    ParkingEntrance,
    ParkingLot,
    ParkingSegment,
    ParkingSpot,
    SourceDataset,
    SourceProvider,
    SourceReference,
    SpotContext,
    SyncStatus,
    SyncTrigger,
    VehicleType,
)
from parking.sync_lock import SyncAlreadyRunningError

pytestmark = [
    pytest.mark.django_db,
    pytest.mark.skipif(
        os.getenv("TEST_WITH_POSTGIS") != "true",
        reason="Admin inspection integration tests require PostGIS",
    ),
]

TEST_STORAGES = {
    **settings.STORAGES,
    "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"},
}


def create_inspection_records():
    lot = ParkingLot.objects.create(
        name="Inspection lot",
        city_code="TNN",
        location=Point(120.2, 23.0, srid=4326),
    )
    ParkingEntrance.objects.create(
        lot=lot,
        access_kind=AccessKind.ENTRANCE,
        location=Point(120.2, 23.0, srid=4326),
    )
    segment = ParkingSegment.objects.create(
        name="Inspection segment",
        city_code="TNN",
        representative_point=Point(120.21, 23.01, srid=4326),
    )
    spot = ParkingSpot.objects.create(
        context=SpotContext.OFF_STREET,
        lot=lot,
        vehicle_type=VehicleType.CAR,
        source_space_type=1,
    )
    ParkingSpot.objects.create(
        context=SpotContext.ON_STREET,
        segment=segment,
        location=Point(120.21, 23.01, srid=4326),
        vehicle_type=VehicleType.MOTORCYCLE,
        source_space_type=2,
    )
    SourceReference.objects.create(
        entity=spot,
        entity_type=EntityKind.SPOT,
        source=SourceProvider.TDX,
        dataset=SourceDataset.OFF_STREET_SPOT,
        authority_code="TNN",
        source_id="inspection-spot",
        identifier_kind=IdentifierKind.PROVIDED,
        last_seen_at=timezone.now(),
    )


def create_admin_user(username="inspector"):
    return get_user_model().objects.create_superuser(
        username=username,
        email=f"{username}@example.com",
        password="test-password",
    )


def test_inspection_context_reports_inventory_and_quality_gaps():
    create_inspection_records()

    context = build_data_inspection_context()

    assert dict(context["entity_counts"])["Parking lots"] == 1
    assert dict(context["entity_counts"])["Off-street spots"] == 1
    assert context["relationship_coverage"][0][1:] == (1, 1)
    assert context["geometry_gaps"][2][1:] == (1, 1)
    assert context["source_coverage"][0]["active"] == 1
    assert {row["vehicle_label"] for row in context["vehicle_coverage"]} == {
        "Car",
        "Motorcycle or scooter",
    }


@override_settings(STORAGES=TEST_STORAGES)
def test_staff_can_open_data_inspection_page(client):
    create_inspection_records()
    client.force_login(create_admin_user())

    response = client.get(reverse("admin:parking_data_inspection"))

    assert response.status_code == 200
    assert b"Parking data inspection" in response.content
    assert b"Inspection lot" not in response.content


@override_settings(STORAGES=TEST_STORAGES)
def test_admin_trigger_runs_shared_sync_service_and_redirects_to_result(client):
    client.force_login(create_admin_user("sync-operator"))
    run_id = uuid4()
    summary = SimpleNamespace(run_id=run_id, status=SyncStatus.SUCCEEDED)

    with (
        patch("parking.admin.single_sync_run", return_value=nullcontext()),
        patch("parking.admin.run_tdx_sync", return_value=summary) as runner,
    ):
        response = client.post(reverse("admin:parking_syncrun_trigger"))

    assert response.status_code == 302
    assert response.url == reverse("admin:parking_syncrun_change", args=(run_id,))
    runner.assert_called_once_with(trigger=SyncTrigger.MANUAL_ADMIN)


@override_settings(STORAGES=TEST_STORAGES)
def test_admin_trigger_rejects_duplicate_execution(client):
    client.force_login(create_admin_user("duplicate-operator"))
    duplicate_lock = MockSyncLockError()

    with (
        patch("parking.admin.single_sync_run", return_value=duplicate_lock),
        patch("parking.admin.run_tdx_sync") as runner,
    ):
        response = client.post(reverse("admin:parking_syncrun_trigger"))

    assert response.status_code == 302
    assert response.url == reverse("admin:parking_syncrun_changelist")
    runner.assert_not_called()


class MockSyncLockError:
    def __enter__(self):
        raise SyncAlreadyRunningError("A tdx sync for Tainan is already running")

    def __exit__(self, *args):
        return False
