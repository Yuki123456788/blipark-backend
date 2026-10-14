"""Transactional persistence for source-neutral parking records."""

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from uuid import UUID

from django.contrib.gis.geos import GEOSGeometry
from django.db import transaction

from .models import (
    EntityKind,
    ParkingEntrance,
    ParkingLot,
    ParkingSegment,
    ParkingSpot,
    SourceDataset,
    SourceReference,
    SpotContext,
)
from .normalization import (
    NormalizedRecord,
    ParkingEntranceRecord,
    ParkingLotRecord,
    ParkingSegmentRecord,
    ParkingSpotRecord,
    SourceIdentity,
)


class UpsertDisposition(StrEnum):
    INSERTED = "inserted"
    UPDATED = "updated"
    UNCHANGED = "unchanged"


@dataclass(frozen=True, slots=True)
class UpsertResult:
    entity_id: UUID
    disposition: UpsertDisposition


class ParkingPersistenceError(RuntimeError):
    pass


class MissingParentError(ParkingPersistenceError):
    pass


class SourceIdentityConflict(ParkingPersistenceError):
    pass


class ParkingRepository:
    @transaction.atomic
    def upsert(self, record: NormalizedRecord, *, seen_at: datetime) -> UpsertResult:
        reference = self._find_reference(record.identity)
        if reference is None:
            entity = self._create(record)
            SourceReference.objects.create(
                entity=entity,
                entity_type=record.identity.entity_type,
                source=record.identity.source,
                dataset=record.identity.dataset,
                authority_code=record.identity.authority_code,
                source_id=record.identity.source_id,
                identifier_kind=record.identity.identifier_kind,
                source_updated_at=record.identity.source_updated_at,
                last_seen_at=seen_at,
                is_active=True,
            )
            return UpsertResult(entity_id=entity.pk, disposition=UpsertDisposition.INSERTED)

        if reference.entity_type != record.identity.entity_type:
            raise SourceIdentityConflict(
                f"Source identity {record.identity.dataset}:{record.identity.source_id} "
                f"points to {reference.entity_type}, expected {record.identity.entity_type}"
            )

        entity = self._get_concrete_entity(reference.entity_id, record.identity.entity_type)
        changed = self._update(entity, record)
        self._touch_reference(reference, record.identity, seen_at)
        disposition = UpsertDisposition.UPDATED if changed else UpsertDisposition.UNCHANGED
        return UpsertResult(entity_id=entity.pk, disposition=disposition)

    def _find_reference(self, identity: SourceIdentity) -> SourceReference | None:
        return (
            SourceReference.objects.select_for_update()
            .filter(
                source=identity.source,
                authority_code=identity.authority_code,
                dataset=identity.dataset,
                source_id=identity.source_id,
            )
            .first()
        )

    def _create(self, record: NormalizedRecord):
        if isinstance(record, ParkingLotRecord):
            return ParkingLot.objects.create(**self._lot_fields(record))
        if isinstance(record, ParkingEntranceRecord):
            return ParkingEntrance.objects.create(
                lot=self._resolve_lot(record),
                **self._entrance_fields(record),
            )
        if isinstance(record, ParkingSegmentRecord):
            return ParkingSegment.objects.create(**self._segment_fields(record))
        if isinstance(record, ParkingSpotRecord):
            parent_fields = self._resolve_spot_parent(record)
            return ParkingSpot.objects.create(**parent_fields, **self._spot_fields(record))
        raise TypeError(f"Unsupported normalized record: {type(record).__name__}")

    def _update(self, entity, record: NormalizedRecord) -> bool:
        if isinstance(record, ParkingLotRecord) and isinstance(entity, ParkingLot):
            fields = self._lot_fields(record)
        elif isinstance(record, ParkingEntranceRecord) and isinstance(entity, ParkingEntrance):
            fields = {"lot": self._resolve_lot(record), **self._entrance_fields(record)}
        elif isinstance(record, ParkingSegmentRecord) and isinstance(entity, ParkingSegment):
            fields = self._segment_fields(record)
        elif isinstance(record, ParkingSpotRecord) and isinstance(entity, ParkingSpot):
            fields = {**self._resolve_spot_parent(record), **self._spot_fields(record)}
        else:
            raise SourceIdentityConflict(
                f"Source identity resolved to {type(entity).__name__}, "
                f"but mapper produced {type(record).__name__}"
            )

        changed = any(
            not self._equal(getattr(entity, name), value) for name, value in fields.items()
        )
        if changed:
            for name, value in fields.items():
                setattr(entity, name, value)
            entity.save()
        return changed

    @staticmethod
    def _touch_reference(
        reference: SourceReference,
        identity: SourceIdentity,
        seen_at: datetime,
    ):
        reference.identifier_kind = identity.identifier_kind
        reference.source_updated_at = identity.source_updated_at
        reference.last_seen_at = seen_at
        reference.is_active = True
        reference.save(
            update_fields=(
                "identifier_kind",
                "source_updated_at",
                "last_seen_at",
                "is_active",
                "updated_at",
            )
        )

    @staticmethod
    def _get_concrete_entity(entity_id: UUID, entity_type: EntityKind):
        models_by_type = {
            EntityKind.LOT: ParkingLot,
            EntityKind.ENTRANCE: ParkingEntrance,
            EntityKind.SEGMENT: ParkingSegment,
            EntityKind.SPOT: ParkingSpot,
        }
        return models_by_type[entity_type].objects.select_for_update().get(pk=entity_id)

    @staticmethod
    def _lot_fields(record: ParkingLotRecord) -> dict:
        return {
            "name": record.name,
            "name_en": record.name_en,
            "short_name": record.short_name,
            "description": record.description,
            "address": record.address,
            "city_code": record.city_code,
            "district_id": record.district_id,
            "district_name": record.district_name,
            "location": record.location,
            "boundary": record.boundary,
            "car_park_type": record.car_park_type,
            "operation_type": record.operation_type,
            "fare_description": record.fare_description,
            "is_public": record.is_public,
            "has_live_occupancy": record.has_live_occupancy,
            "has_ev_charging": record.has_ev_charging,
            "is_wheelchair_accessible": record.is_wheelchair_accessible,
            "allows_overnight": record.allows_overnight,
        }

    @staticmethod
    def _entrance_fields(record: ParkingEntranceRecord) -> dict:
        return {
            "access_kind": record.access_kind,
            "name": record.name,
            "location": record.location,
            "access_type": record.access_type,
            "max_height_cm": record.max_height_cm,
            "max_width_cm": record.max_width_cm,
            "max_weight_kg": record.max_weight_kg,
            "road_name": record.road_name,
            "bearing": record.bearing,
        }

    @staticmethod
    def _segment_fields(record: ParkingSegmentRecord) -> dict:
        return {
            "name": record.name,
            "name_en": record.name_en,
            "description": record.description,
            "fare_description": record.fare_description,
            "city_code": record.city_code,
            "district_id": record.district_id,
            "district_name": record.district_name,
            "representative_point": record.representative_point,
            "geometry": record.geometry,
            "has_charging_point": record.has_charging_point,
        }

    @staticmethod
    def _spot_fields(record: ParkingSpotRecord) -> dict:
        return {
            "context": record.context,
            "location": record.location,
            "footprint": record.footprint,
            "vehicle_type": record.vehicle_type,
            "source_space_type": record.source_space_type,
            "has_charging_point": record.has_charging_point,
            "floor": record.floor,
            "length_cm": record.length_cm,
            "width_cm": record.width_cm,
        }

    @staticmethod
    def _resolve_lot(record: ParkingEntranceRecord) -> ParkingLot:
        reference = SourceReference.objects.filter(
            source=record.identity.source,
            authority_code=record.identity.authority_code,
            dataset=SourceDataset.CAR_PARK,
            source_id=record.lot_source_id,
            entity_type=EntityKind.LOT,
        ).first()
        if reference is None:
            raise MissingParentError(f"Parking lot source ID {record.lot_source_id} was not found")
        return ParkingLot.objects.get(pk=reference.entity_id)

    @staticmethod
    def _resolve_spot_parent(record: ParkingSpotRecord) -> dict:
        if record.context == SpotContext.OFF_STREET:
            dataset = SourceDataset.CAR_PARK
            entity_type = EntityKind.LOT
            model = ParkingLot
            field_name = "lot"
            empty_field = "segment"
        else:
            dataset = SourceDataset.PARKING_SEGMENT
            entity_type = EntityKind.SEGMENT
            model = ParkingSegment
            field_name = "segment"
            empty_field = "lot"

        reference = SourceReference.objects.filter(
            source=record.identity.source,
            authority_code=record.identity.authority_code,
            dataset=dataset,
            source_id=record.parent_source_id,
            entity_type=entity_type,
        ).first()
        if reference is None:
            raise MissingParentError(
                f"{entity_type.label} source ID {record.parent_source_id} was not found"
            )
        return {field_name: model.objects.get(pk=reference.entity_id), empty_field: None}

    @staticmethod
    def _equal(left, right) -> bool:
        if isinstance(left, GEOSGeometry) and isinstance(right, GEOSGeometry):
            return left.srid == right.srid and left.equals_exact(right, 0)
        return left == right
