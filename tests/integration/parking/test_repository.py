import os
from dataclasses import replace
from datetime import datetime, timedelta

import pytest
from django.contrib.gis.geos import Point
from django.utils import timezone

from parking.models import (
    AccessKind,
    EntityKind,
    IdentifierKind,
    ParkingEntity,
    ParkingLot,
    ParkingSpot,
    SourceDataset,
    SourceProvider,
    SourceReference,
    SpotContext,
    VehicleType,
)
from parking.normalization import (
    ParkingEntranceRecord,
    ParkingLotRecord,
    ParkingSpotRecord,
    SourceIdentity,
)
from parking.repositories import MissingParentError, ParkingRepository, UpsertDisposition

pytestmark = [
    pytest.mark.django_db,
    pytest.mark.skipif(
        os.getenv("TEST_WITH_POSTGIS") != "true",
        reason="PostGIS integration tests require TEST_WITH_POSTGIS=true",
    ),
]


def identity(entity_type, dataset, source_id, *, source_scope="", source_discriminator=""):
    return SourceIdentity(
        entity_type=entity_type,
        source=SourceProvider.TDX,
        dataset=dataset,
        authority_code="TNN",
        source_id=source_id,
        source_scope=source_scope,
        source_discriminator=source_discriminator,
        identifier_kind=IdentifierKind.PROVIDED,
        source_updated_at=datetime.fromisoformat("2026-10-03T03:05:59+08:00"),
    )


def lot_record(name="Test lot", source_id="lot-1"):
    return ParkingLotRecord(
        identity=identity(EntityKind.LOT, SourceDataset.CAR_PARK, source_id),
        name=name,
        name_en="",
        short_name="",
        description="",
        address="Tainan",
        city_code="TNN",
        district_id="",
        district_name="",
        location=Point(120.2, 23.0, srid=4326),
        boundary=None,
        car_park_type=1,
        operation_type=1,
        fare_description="",
        is_public=True,
        has_live_occupancy=False,
        has_ev_charging=False,
        is_wheelchair_accessible=False,
        allows_overnight=True,
    )


def test_lot_upsert_is_idempotent_and_tracks_real_updates():
    repository = ParkingRepository()
    first_seen = timezone.now()
    second_seen = first_seen + timedelta(microseconds=1)

    inserted = repository.upsert(lot_record(), seen_at=first_seen)
    unchanged = repository.upsert(lot_record(), seen_at=second_seen)
    updated = repository.upsert(replace(lot_record(), name="Renamed lot"), seen_at=second_seen)

    assert inserted.disposition == UpsertDisposition.INSERTED
    assert unchanged.disposition == UpsertDisposition.UNCHANGED
    assert updated.disposition == UpsertDisposition.UPDATED
    assert inserted.entity_id == unchanged.entity_id == updated.entity_id
    assert ParkingLot.objects.get().name == "Renamed lot"
    assert ParkingEntity.objects.count() == 1
    assert SourceReference.objects.get().last_seen_at == second_seen


def test_spot_upsert_resolves_parent_through_source_reference():
    repository = ParkingRepository()
    seen_at = timezone.now()
    lot = repository.upsert(lot_record(), seen_at=seen_at)
    spot_record = ParkingSpotRecord(
        identity=identity(EntityKind.SPOT, SourceDataset.OFF_STREET_SPOT, "spot-1"),
        context=SpotContext.OFF_STREET,
        parent_source_id="lot-1",
        location=None,
        footprint=None,
        vehicle_type=VehicleType.CAR,
        source_space_type=1,
        has_charging_point=False,
        floor="B1",
        length_cm=None,
        width_cm=None,
    )

    result = repository.upsert(spot_record, seen_at=seen_at)

    spot = ParkingSpot.objects.get(pk=result.entity_id)
    assert spot.lot_id == lot.entity_id
    assert spot.segment_id is None


def test_spot_identity_can_repeat_across_scopes_and_discriminators():
    repository = ParkingRepository()
    seen_at = timezone.now()
    repository.upsert(lot_record(source_id="lot-1"), seen_at=seen_at)
    repository.upsert(lot_record(source_id="lot-2"), seen_at=seen_at)

    def spot(parent_source_id, discriminator):
        return ParkingSpotRecord(
            identity=identity(
                EntityKind.SPOT,
                SourceDataset.OFF_STREET_SPOT,
                "reused-spot-id",
                source_scope=parent_source_id,
                source_discriminator=discriminator,
            ),
            context=SpotContext.OFF_STREET,
            parent_source_id=parent_source_id,
            location=None,
            footprint=None,
            vehicle_type=VehicleType.CAR,
            source_space_type=1,
            has_charging_point=False,
            floor="",
            length_cm=None,
            width_cm=None,
        )

    first = repository.upsert(spot("lot-1", "attrs:a"), seen_at=seen_at)
    second = repository.upsert(spot("lot-2", "attrs:a"), seen_at=seen_at)
    third = repository.upsert(spot("lot-1", "attrs:b"), seen_at=seen_at)

    assert len({first.entity_id, second.entity_id, third.entity_id}) == 3
    assert SourceReference.objects.filter(source_id="reused-spot-id").count() == 3


def test_missing_parent_fails_without_partial_entity():
    repository = ParkingRepository()
    seen_at = timezone.now()
    entrance = ParkingEntranceRecord(
        identity=replace(
            identity(EntityKind.ENTRANCE, SourceDataset.ENTRANCE_EXIT, "derived-1"),
            identifier_kind=IdentifierKind.DERIVED,
        ),
        lot_source_id="missing-lot",
        access_kind=AccessKind.ENTRANCE,
        name="Entrance",
        location=Point(120.2, 23.0, srid=4326),
        access_type=1,
        max_height_cm=None,
        max_width_cm=None,
        max_weight_kg=None,
        road_name="",
        bearing="",
    )

    with pytest.raises(MissingParentError, match="missing-lot"):
        repository.upsert(entrance, seen_at=seen_at)

    assert ParkingEntity.objects.count() == 0
    assert SourceReference.objects.count() == 0
