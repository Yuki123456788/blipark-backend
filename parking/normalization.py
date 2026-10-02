"""Source-neutral records accepted by the parking persistence boundary."""

from dataclasses import dataclass
from datetime import datetime

from django.contrib.gis.geos import GEOSGeometry, Point

from .models import (
    AccessKind,
    EntityKind,
    IdentifierKind,
    SourceDataset,
    SourceProvider,
    SpotContext,
    VehicleType,
)


@dataclass(frozen=True, slots=True)
class SourceIdentity:
    entity_type: EntityKind
    source: SourceProvider
    dataset: SourceDataset
    authority_code: str
    source_id: str
    identifier_kind: IdentifierKind
    source_updated_at: datetime | None


@dataclass(frozen=True, slots=True)
class ParkingLotRecord:
    identity: SourceIdentity
    name: str
    name_en: str
    short_name: str
    description: str
    address: str
    city_code: str
    district_id: str
    district_name: str
    location: Point
    boundary: GEOSGeometry | None
    car_park_type: int | None
    operation_type: int | None
    fare_description: str
    is_public: bool | None
    has_live_occupancy: bool | None
    has_ev_charging: bool | None
    is_wheelchair_accessible: bool | None
    allows_overnight: bool | None


@dataclass(frozen=True, slots=True)
class ParkingEntranceRecord:
    identity: SourceIdentity
    lot_source_id: str
    access_kind: AccessKind
    name: str
    location: Point
    access_type: int | None
    max_height_cm: float | None
    max_width_cm: float | None
    max_weight_kg: float | None
    road_name: str
    bearing: str


@dataclass(frozen=True, slots=True)
class ParkingSegmentRecord:
    identity: SourceIdentity
    name: str
    name_en: str
    description: str
    fare_description: str
    city_code: str
    district_id: str
    district_name: str
    representative_point: Point
    geometry: GEOSGeometry | None
    has_charging_point: bool | None


@dataclass(frozen=True, slots=True)
class ParkingSpotRecord:
    identity: SourceIdentity
    context: SpotContext
    parent_source_id: str
    location: Point | None
    footprint: GEOSGeometry | None
    vehicle_type: VehicleType
    source_space_type: int
    has_charging_point: bool
    floor: str
    length_cm: float | None
    width_cm: float | None


NormalizedRecord = (
    ParkingLotRecord | ParkingEntranceRecord | ParkingSegmentRecord | ParkingSpotRecord
)
