from django.contrib import admin
from django.test import SimpleTestCase

from parking.models import (
    ParkingEntrance,
    ParkingLot,
    ParkingSegment,
    ParkingSpot,
    SourceReference,
)


class ParkingAdminRegistrationTest(SimpleTestCase):
    def test_phase_zero_models_are_inspectable_in_admin(self):
        for model in (
            ParkingLot,
            ParkingEntrance,
            ParkingSegment,
            ParkingSpot,
            SourceReference,
        ):
            assert model in admin.site._registry

    def test_source_reference_admin_exposes_sync_identity_and_state(self):
        model_admin = admin.site._registry[SourceReference]

        assert {
            "source",
            "authority_code",
            "dataset",
            "source_id",
            "entity_type",
            "is_active",
            "last_seen_at",
        }.issubset(model_admin.list_display)
