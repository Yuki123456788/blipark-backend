"""Anti-corruption mapper from TDX DTOs to source-neutral parking records."""

import hashlib
import json
from collections import Counter

from django.contrib.gis.geos import GEOSException, GEOSGeometry, Point

from parking.models import (
    AccessKind,
    EntityKind,
    IdentifierKind,
    SourceDataset,
    SourceProvider,
    SpotContext,
    VehicleType,
)
from parking.normalization import (
    ParkingEntranceRecord,
    ParkingLotRecord,
    ParkingSegmentRecord,
    ParkingSpotRecord,
    SourceIdentity,
)

from .schemas import (
    TDXAccessPoint,
    TDXCarPark,
    TDXOffStreetSpotGroup,
    TDXOnStreetSpot,
    TDXParkingEntranceExit,
    TDXParkingSegment,
    TDXParkingWrapper,
)

CAR_SPACE_TYPES = {1, 7, 8, 9, 11, 15, 17, 19, 21, 23, 26, 27, 28, 29}
MOTORCYCLE_SPACE_TYPES = {2, 10, 12, 14, 16, 18, 20, 22}


class TDXMappingError(ValueError):
    pass


def map_car_park(record: TDXCarPark, metadata: TDXParkingWrapper) -> ParkingLotRecord:
    _assert_authority(record.city_code, metadata)
    return ParkingLotRecord(
        identity=_identity(
            EntityKind.LOT,
            SourceDataset.CAR_PARK,
            metadata,
            record.car_park_id,
        ),
        name=record.name.primary or "",
        name_en=_text(record.name.en),
        short_name=_name_text(record.short_name),
        description=_text(record.description),
        address=_text(record.address),
        city_code=record.city_code,
        district_id=_text(record.town_id),
        district_name=_text(record.town_name),
        location=_point(record.position.longitude, record.position.latitude),
        boundary=_geometry(record.geometry_wkt, allowed_types={"Polygon", "MultiPolygon"}),
        car_park_type=record.car_park_type,
        operation_type=record.operation_type,
        fare_description=_text(record.fare_description),
        is_public=_flag(record.is_public),
        has_live_occupancy=_flag(record.live_occupancy_available),
        has_ev_charging=_flag(record.ev_recharging_available),
        is_wheelchair_accessible=_flag(record.wheelchair_accessible),
        allows_overnight=_flag(record.overnight_permitted),
    )


def map_parking_entrances(
    group: TDXParkingEntranceExit,
    metadata: TDXParkingWrapper,
) -> list[ParkingEntranceRecord]:
    counters: Counter[str] = Counter()
    records: list[ParkingEntranceRecord] = []
    groups = (
        (AccessKind.ENTRANCE, group.entrances),
        (AccessKind.EXIT, group.exits),
        (AccessKind.ENTRANCE_EXIT, group.entrance_exits),
    )
    for access_kind, access_points in groups:
        for access_point in access_points:
            base_id = _entrance_source_id(group.car_park_id, access_kind, access_point)
            occurrence = counters[base_id]
            counters[base_id] += 1
            source_id = base_id if occurrence == 0 else f"{base_id}:{occurrence}"
            records.append(
                ParkingEntranceRecord(
                    identity=_identity(
                        EntityKind.ENTRANCE,
                        SourceDataset.ENTRANCE_EXIT,
                        metadata,
                        source_id,
                        identifier_kind=IdentifierKind.DERIVED,
                    ),
                    lot_source_id=group.car_park_id,
                    access_kind=access_kind,
                    name=_name_text(access_point.name),
                    location=_point(
                        access_point.position.longitude,
                        access_point.position.latitude,
                    ),
                    access_type=access_point.access_type,
                    max_height_cm=access_point.max_allowed_height,
                    max_width_cm=access_point.max_allowed_width,
                    max_weight_kg=access_point.max_allowed_weight,
                    road_name=_text(access_point.road_name),
                    bearing=_text(access_point.bearing),
                )
            )
    return records


def map_parking_segment(
    record: TDXParkingSegment,
    metadata: TDXParkingWrapper,
) -> ParkingSegmentRecord:
    _assert_authority(record.city_code, metadata)
    return ParkingSegmentRecord(
        identity=_identity(
            EntityKind.SEGMENT,
            SourceDataset.PARKING_SEGMENT,
            metadata,
            record.parking_segment_id,
        ),
        name=record.name.primary or "",
        name_en=_text(record.name.en),
        description=_text(record.description),
        fare_description=_text(record.fare_description),
        city_code=record.city_code,
        district_id=_text(record.town_id),
        district_name=_text(record.town_name),
        representative_point=_point(record.position.longitude, record.position.latitude),
        geometry=_geometry(record.geometry_wkt, allowed_types={"LineString"}),
        has_charging_point=_flag(record.has_charging_point),
    )


def map_off_street_spots(
    group: TDXOffStreetSpotGroup,
    metadata: TDXParkingWrapper,
) -> list[ParkingSpotRecord]:
    return [
        ParkingSpotRecord(
            identity=_identity(
                EntityKind.SPOT,
                SourceDataset.OFF_STREET_SPOT,
                metadata,
                spot.parking_spot_id,
                source_scope=group.car_park_id,
                source_discriminator=_off_street_spot_discriminator(spot),
            ),
            context=SpotContext.OFF_STREET,
            parent_source_id=group.car_park_id,
            location=None,
            footprint=None,
            vehicle_type=normalize_vehicle_type(spot.space_type),
            source_space_type=spot.space_type,
            has_charging_point=bool(spot.has_charging_point),
            floor=_text(spot.floor),
            length_cm=spot.length_cm,
            width_cm=spot.width_cm,
        )
        for spot in group.spots
    ]


def map_on_street_spot(
    record: TDXOnStreetSpot,
    metadata: TDXParkingWrapper,
) -> ParkingSpotRecord:
    return ParkingSpotRecord(
        identity=_identity(
            EntityKind.SPOT,
            SourceDataset.ON_STREET_SPOT,
            metadata,
            record.parking_spot_id,
            source_scope=record.parking_segment_id,
            source_discriminator=_position_discriminator(record.position),
        ),
        context=SpotContext.ON_STREET,
        parent_source_id=record.parking_segment_id,
        location=_point(record.position.longitude, record.position.latitude),
        footprint=_geometry(record.geometry_wkt, allowed_types={"Polygon", "MultiPolygon"}),
        vehicle_type=normalize_vehicle_type(record.space_type),
        source_space_type=record.space_type,
        has_charging_point=bool(record.has_charging_point),
        floor="",
        length_cm=record.length_cm,
        width_cm=record.width_cm,
    )


def normalize_vehicle_type(space_type: int) -> VehicleType:
    if space_type in CAR_SPACE_TYPES:
        return VehicleType.CAR
    if space_type in MOTORCYCLE_SPACE_TYPES:
        return VehicleType.MOTORCYCLE
    if space_type == 3:
        return VehicleType.HEAVY_MOTORCYCLE
    return VehicleType.OTHER


def _identity(
    entity_type: EntityKind,
    dataset: SourceDataset,
    metadata: TDXParkingWrapper,
    source_id: str,
    *,
    source_scope: str = "",
    source_discriminator: str = "",
    identifier_kind: IdentifierKind = IdentifierKind.PROVIDED,
) -> SourceIdentity:
    return SourceIdentity(
        entity_type=entity_type,
        source=SourceProvider.TDX,
        dataset=dataset,
        authority_code=metadata.authority_code,
        source_id=source_id,
        source_scope=source_scope,
        source_discriminator=source_discriminator,
        identifier_kind=identifier_kind,
        source_updated_at=metadata.source_updated_at,
    )


def _point(longitude: float, latitude: float) -> Point:
    return Point(longitude, latitude, srid=4326)


def _geometry(value: str | None, *, allowed_types: set[str]) -> GEOSGeometry | None:
    if not value:
        return None
    try:
        geometry = GEOSGeometry(value, srid=4326)
    except (GEOSException, ValueError) as error:
        raise TDXMappingError("TDX geometry is not valid WKT") from error
    if geometry.geom_type not in allowed_types:
        raise TDXMappingError(
            f"TDX geometry type {geometry.geom_type} is not one of {sorted(allowed_types)}"
        )
    if geometry.srid is None:
        geometry.srid = 4326
    if geometry.srid != 4326:
        raise TDXMappingError(f"TDX geometry SRID must be 4326, got {geometry.srid}")
    return geometry


def _assert_authority(city_code: str, metadata: TDXParkingWrapper):
    if city_code != metadata.authority_code:
        raise TDXMappingError(
            f"TDX record city code {city_code} did not match authority {metadata.authority_code}"
        )


def _entrance_source_id(
    car_park_id: str,
    access_kind: AccessKind,
    access_point: TDXAccessPoint,
) -> str:
    longitude = f"{access_point.position.longitude:.7f}"
    latitude = f"{access_point.position.latitude:.7f}"
    return f"{car_park_id}:{access_kind}:{longitude}:{latitude}"


def _off_street_spot_discriminator(spot) -> str:
    payload = (
        spot.space_type,
        bool(spot.has_charging_point),
        _text(spot.floor),
        spot.length_cm,
        spot.width_cm,
    )
    canonical = json.dumps(payload, ensure_ascii=True, separators=(",", ":"))
    return f"attrs:{hashlib.sha256(canonical.encode()).hexdigest()[:32]}"


def _position_discriminator(position) -> str:
    return f"position:{position.longitude:.7f}:{position.latitude:.7f}"


def _flag(value: int | None) -> bool | None:
    return None if value is None else bool(value)


def _text(value: str | None) -> str:
    return value.strip() if value else ""


def _name_text(value) -> str:
    return value.primary if value and value.primary else ""
