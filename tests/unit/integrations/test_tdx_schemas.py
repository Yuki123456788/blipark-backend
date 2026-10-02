import copy
import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from integrations.tdx.schemas import (
    TDXCarParkResponse,
    TDXOffStreetSpotResponse,
    TDXOnStreetSpotResponse,
    TDXParkingEntranceExitResponse,
    TDXParkingSegmentResponse,
)

FIXTURE_DIR = Path(__file__).parents[2] / "fixtures" / "tdx"


@pytest.mark.parametrize(
    ("filename", "schema", "records_alias"),
    [
        ("car_parks.json", TDXCarParkResponse, "CarParks"),
        (
            "parking_entrance_exits.json",
            TDXParkingEntranceExitResponse,
            "ParkingEntranceExits",
        ),
        ("off_street_parking_spots.json", TDXOffStreetSpotResponse, "ParkingSpots"),
        ("parking_segments.json", TDXParkingSegmentResponse, "ParkingSegments"),
        (
            "on_street_parking_spots.json",
            TDXOnStreetSpotResponse,
            "ParkingSegmentSpots",
        ),
    ],
)
def test_sanitized_live_fixture_matches_schema(filename, schema, records_alias):
    payload = json.loads((FIXTURE_DIR / filename).read_text())

    response = schema.model_validate(payload)

    assert response.authority_code == "TNN"
    assert response.records
    assert records_alias in response.model_dump(by_alias=True)
    assert "Items" not in response.model_dump(by_alias=True)


def test_coordinate_order_and_bounds_are_validated():
    payload = json.loads((FIXTURE_DIR / "car_parks.json").read_text())
    payload["CarParks"][0]["CarParkPosition"] = {
        "PositionLat": 120.21046,
        "PositionLon": 22.99106,
    }

    with pytest.raises(ValidationError, match="PositionLat"):
        TDXCarParkResponse.model_validate(payload)


def test_binary_source_flags_are_not_coerced_or_silently_accepted():
    payload = json.loads((FIXTURE_DIR / "car_parks.json").read_text())
    payload["CarParks"][0]["IsPublic"] = 2

    with pytest.raises(ValidationError, match="IsPublic"):
        TDXCarParkResponse.model_validate(payload)


def test_unknown_source_fields_fail_as_schema_drift():
    payload = json.loads((FIXTURE_DIR / "parking_segments.json").read_text())
    payload["ParkingSegments"][0]["UnexpectedField"] = "drift"

    with pytest.raises(ValidationError, match="UnexpectedField"):
        TDXParkingSegmentResponse.model_validate(payload)


def test_required_source_identifier_cannot_be_blank():
    payload = json.loads((FIXTURE_DIR / "on_street_parking_spots.json").read_text())
    invalid = copy.deepcopy(payload)
    invalid["ParkingSegmentSpots"][0]["ParkingSpotID"] = "  "

    with pytest.raises(ValidationError, match="ParkingSpotID"):
        TDXOnStreetSpotResponse.model_validate(invalid)
