import json
from pathlib import Path

import pytest

from integrations.tdx.mapper import (
    TDXMappingError,
    map_car_park,
    map_off_street_spots,
    map_on_street_spot,
    map_parking_entrances,
    map_parking_segment,
    normalize_vehicle_type,
)
from integrations.tdx.schemas import (
    TDXCarParkResponse,
    TDXOffStreetSpotResponse,
    TDXOnStreetSpotResponse,
    TDXParkingEntranceExitResponse,
    TDXParkingSegmentResponse,
)
from parking.models import AccessKind, IdentifierKind, SpotContext, VehicleType

FIXTURE_DIR = Path(__file__).parents[3] / "fixtures" / "tdx"


def load_fixture(filename, schema):
    return schema.model_validate_json((FIXTURE_DIR / filename).read_text())


def test_car_park_mapper_keeps_lon_lat_order_and_domain_fields():
    response = load_fixture("car_parks.json", TDXCarParkResponse)

    record = map_car_park(response.records[0], response)

    assert record.name == "萬昌街停車場"
    assert record.location.x == 120.21046
    assert record.location.y == 22.99106
    assert record.location.srid == 4326
    assert record.identity.source_id == "89096083"
    assert record.is_public is True
    assert record.has_ev_charging is True


def test_entrance_mapper_flattens_each_access_kind_with_derived_identity():
    response = load_fixture("parking_entrance_exits.json", TDXParkingEntranceExitResponse)

    records = map_parking_entrances(response.records[0], response)

    assert [record.access_kind for record in records] == [AccessKind.ENTRANCE, AccessKind.EXIT]
    assert all(record.identity.identifier_kind == IdentifierKind.DERIVED for record in records)
    assert records[0].identity.source_id == "85744208:entrance:120.2214000:22.9828000"
    assert records[0].lot_source_id == "85744208"


def test_off_street_spot_mapper_preserves_missing_location_and_source_subtypes():
    response = load_fixture("off_street_parking_spots.json", TDXOffStreetSpotResponse)

    records = map_off_street_spots(response.records[0], response)

    assert [record.vehicle_type for record in records] == [
        VehicleType.CAR,
        VehicleType.CAR,
        VehicleType.CAR,
    ]
    assert all(record.context == SpotContext.OFF_STREET for record in records)
    assert all(record.location is None for record in records)
    assert records[2].source_space_type == 11
    assert records[2].has_charging_point is True


def test_segment_and_on_street_spot_map_parent_and_geometry():
    segment_response = load_fixture("parking_segments.json", TDXParkingSegmentResponse)
    spot_response = load_fixture("on_street_parking_spots.json", TDXOnStreetSpotResponse)

    segment = map_parking_segment(segment_response.records[0], segment_response)
    spot = map_on_street_spot(spot_response.records[0], spot_response)

    assert segment.representative_point.tuple == (120.20486, 22.99815)
    assert segment.geometry is None
    assert spot.context == SpotContext.ON_STREET
    assert spot.parent_source_id == "1408"
    assert spot.location.tuple == (120.23821, 23.02357)


@pytest.mark.parametrize(
    ("space_type", "expected"),
    [
        (1, VehicleType.CAR),
        (9, VehicleType.CAR),
        (2, VehicleType.MOTORCYCLE),
        (10, VehicleType.MOTORCYCLE),
        (3, VehicleType.HEAVY_MOTORCYCLE),
        (4, VehicleType.OTHER),
        (999, VehicleType.OTHER),
    ],
)
def test_vehicle_type_normalization(space_type, expected):
    assert normalize_vehicle_type(space_type) == expected


def test_mapper_rejects_geometry_type_that_does_not_match_domain_field():
    payload = json.loads((FIXTURE_DIR / "parking_segments.json").read_text())
    payload["ParkingSegments"][0]["Geometry"] = "POINT (120.1 23.1)"
    response = TDXParkingSegmentResponse.model_validate(payload)

    with pytest.raises(TDXMappingError, match="Point"):
        map_parking_segment(response.records[0], response)


def test_mapper_rejects_record_from_another_authority():
    payload = json.loads((FIXTURE_DIR / "car_parks.json").read_text())
    payload["CarParks"][0]["CityCode"] = "KHH"
    response = TDXCarParkResponse.model_validate(payload)

    with pytest.raises(TDXMappingError, match="KHH.*TNN"):
        map_car_park(response.records[0], response)
