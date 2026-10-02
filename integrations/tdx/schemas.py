"""Validated DTOs for the TDX parking v1 boundary.

The aliases intentionally mirror TDX JSON.  Domain and ORM code must only see the
Python-side names after the mapper has translated these DTOs.
"""

from datetime import datetime
from typing import Annotated, Any

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    StringConstraints,
    model_validator,
)

NonEmptyStr = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]
TDXFlag = Annotated[int, Field(ge=0, le=1)]


class TDXModel(BaseModel):
    """Strict source model that fails loudly when the known contract drifts."""

    model_config = ConfigDict(extra="forbid", strict=True, populate_by_name=True)


class TDXName(TDXModel):
    zh_tw: str | None = Field(default=None, alias="Zh_tw")
    en: str | None = Field(default=None, alias="En")

    @property
    def primary(self) -> str | None:
        return next(
            (value.strip() for value in (self.zh_tw, self.en) if value and value.strip()),
            None,
        )


class TDXPoint(TDXModel):
    latitude: Annotated[float, Field(ge=-90, le=90)] = Field(alias="PositionLat")
    longitude: Annotated[float, Field(ge=-180, le=180)] = Field(alias="PositionLon")


class TDXParkingWrapper(TDXModel):
    source_updated_at: datetime = Field(alias="SrcUpdateTime", strict=False)
    source_update_interval: int = Field(alias="SrcUpdateInterval")
    updated_at: datetime = Field(alias="UpdateTime", strict=False)
    update_interval: Annotated[int, Field(ge=0)] = Field(alias="UpdateInterval")
    authority_code: NonEmptyStr = Field(alias="AuthorityCode")
    version_id: int = Field(alias="VersionID")
    count: Annotated[int, Field(ge=0)] | None = Field(default=None, alias="Count")

    @model_validator(mode="after")
    def timestamps_are_timezone_aware(self):
        if self.source_updated_at.utcoffset() is None or self.updated_at.utcoffset() is None:
            raise ValueError("TDX update timestamps must include a UTC offset")
        return self


class TDXCarPark(TDXModel):
    car_park_id: NonEmptyStr = Field(alias="CarParkID")
    name: TDXName = Field(alias="CarParkName")
    short_name: TDXName | None = Field(default=None, alias="CarParkShortName")
    registration_number: str | None = Field(default=None, alias="CarParkRegNo")
    operator_id: str | None = Field(default=None, alias="OperatorID")
    geometry_wkt: str | None = Field(default=None, alias="Geometry")
    description: str | None = Field(default=None, alias="Description")
    car_park_type: int | None = Field(default=None, alias="CarParkType")
    parking_guide_type: int | None = Field(default=None, alias="ParkingGuideType")
    parking_areas: list[dict[str, Any]] | None = Field(default=None, alias="ParkingAreas")
    parking_types: list[int] = Field(default_factory=list, alias="ParkingTypes")
    parking_site_types: list[int] = Field(default_factory=list, alias="ParkingSiteTypes")
    charge_types: list[int] = Field(default_factory=list, alias="ChargeTypes")
    telephone: str | None = Field(default=None, alias="Telephone")
    emergency_phone: str | None = Field(default=None, alias="EmergencyPhone")
    position: TDXPoint = Field(alias="CarParkPosition")
    email: str | None = Field(default=None, alias="Email")
    address: str | None = Field(default=None, alias="Address")
    image_urls: list[str] | None = Field(default=None, alias="ImageURLs")
    web_url: str | None = Field(default=None, alias="WebURL")
    fare_url: str | None = Field(default=None, alias="FareURL")
    fare_description: str | None = Field(default=None, alias="FareDescription")
    special_offer_description: str | None = Field(default=None, alias="SpecialOfferDescription")
    is_free_out_of_hours: TDXFlag | None = Field(default=None, alias="IsFreeParkingOutOfHours")
    vehicle_restriction: str | None = Field(default=None, alias="VehicleRestriction")
    is_public: TDXFlag | None = Field(default=None, alias="IsPublic")
    is_motorcycle: TDXFlag | None = Field(default=None, alias="IsMotorcycle")
    operation_type: int | None = Field(default=None, alias="OperationType")
    live_occupancy_available: TDXFlag | None = Field(default=None, alias="LiveOccuppancyAvailable")
    ev_recharging_available: TDXFlag | None = Field(default=None, alias="EVRechargingAvailable")
    monthly_ticket_available: TDXFlag | None = Field(default=None, alias="MonthlyTicketAvailable")
    season_ticket_available: TDXFlag | None = Field(default=None, alias="SeasonTicketAvailable")
    reservation_available: TDXFlag | None = Field(default=None, alias="ReservationAvailable")
    reservation_url: str | None = Field(default=None, alias="ReservationURL")
    reservation_description: str | None = Field(default=None, alias="ReservationDescription")
    wheelchair_accessible: TDXFlag | None = Field(default=None, alias="WheelchairAccessible")
    overnight_permitted: TDXFlag | None = Field(default=None, alias="OvernightPermitted")
    ticket_machine: TDXFlag | None = Field(default=None, alias="TicketMachine")
    toilet: TDXFlag | None = Field(default=None, alias="Toilet")
    restaurant: TDXFlag | None = Field(default=None, alias="Restaurant")
    gas_station: TDXFlag | None = Field(default=None, alias="GasStation")
    shop: TDXFlag | None = Field(default=None, alias="Shop")
    gated: TDXFlag | None = Field(default=None, alias="Gated")
    lighting: TDXFlag | None = Field(default=None, alias="Lighting")
    secure_parking: TDXFlag | None = Field(default=None, alias="SecureParking")
    ticket_office: TDXFlag | None = Field(default=None, alias="TicketOffice")
    hazardous_material_loads_prohibited: TDXFlag | None = Field(
        default=None, alias="ProhibitedForAnyHazardousMaterialLoads"
    )
    security_guard: TDXFlag | None = Field(default=None, alias="SecurityGuard")
    supervision: TDXFlag | None = Field(default=None, alias="Supervision")
    supervision_type: int | None = Field(default=None, alias="SupervisionType")
    landmark: str | None = Field(default=None, alias="LandMark")
    building_name: str | None = Field(default=None, alias="BuildingName")
    location_map_url: str | None = Field(default=None, alias="LocationMapURL")
    city: NonEmptyStr = Field(alias="City")
    city_code: NonEmptyStr = Field(alias="CityCode")
    town_name: str | None = Field(default=None, alias="TownName")
    town_id: str | None = Field(default=None, alias="TownID")

    @model_validator(mode="after")
    def has_name(self):
        if self.name.primary is None:
            raise ValueError("CarParkName must contain Zh_tw or En")
        return self


class TDXCarParkResponse(TDXParkingWrapper):
    records: list[TDXCarPark] = Field(alias="CarParks")


class TDXAccessPoint(TDXModel):
    position: TDXPoint = Field(alias="Position")
    access_type: int = Field(alias="Type")
    max_allowed_width: float | None = Field(default=None, alias="MaxAllowedWidth")
    max_allowed_height: float | None = Field(default=None, alias="MaxAllowedHeight")
    max_allowed_weight: float | None = Field(default=None, alias="MaxAllowedWeight")
    road_id: str | None = Field(default=None, alias="RoadID")
    road_name: str | None = Field(default=None, alias="RoadName")
    cross_road_name: str | None = Field(default=None, alias="CrossRoadName")
    link_id: str | None = Field(default=None, alias="LinkID")
    bearing: str | None = Field(default=None, alias="Bearing")


class TDXEntrance(TDXAccessPoint):
    name: TDXName | None = Field(default=None, alias="EntranceName")


class TDXExit(TDXAccessPoint):
    name: TDXName | None = Field(default=None, alias="ExitName")


class TDXEntranceExit(TDXAccessPoint):
    name: TDXName | None = Field(default=None, alias="EntranceExitName")


class TDXParkingEntranceExit(TDXModel):
    car_park_id: NonEmptyStr = Field(alias="CarParkID")
    car_park_name: TDXName = Field(alias="CarParkName")
    entrance_exit_type: int = Field(alias="EntranceExitType")
    entrances: list[TDXEntrance] = Field(alias="Entrances")
    exits: list[TDXExit] = Field(alias="Exits")
    entrance_exits: list[TDXEntranceExit] = Field(alias="EntranceExits")


class TDXParkingEntranceExitResponse(TDXParkingWrapper):
    records: list[TDXParkingEntranceExit] = Field(alias="ParkingEntranceExits")


class TDXOffStreetSpot(TDXModel):
    parking_spot_id: NonEmptyStr = Field(alias="ParkingSpotID")
    space_type: int = Field(alias="SpaceType")
    has_charging_point: TDXFlag = Field(alias="HasChargingPoint")
    length_cm: float | None = Field(default=None, alias="Length")
    width_cm: float | None = Field(default=None, alias="Width")
    floor: str | None = Field(default=None, alias="Floor")


class TDXOffStreetSpotGroup(TDXModel):
    car_park_id: NonEmptyStr = Field(alias="CarParkID")
    car_park_name: TDXName = Field(alias="CarParkName")
    spots: list[TDXOffStreetSpot] = Field(alias="Spots")


class TDXOffStreetSpotResponse(TDXParkingWrapper):
    records: list[TDXOffStreetSpotGroup] = Field(alias="ParkingSpots")


class TDXParkingSegment(TDXModel):
    parking_segment_id: NonEmptyStr = Field(alias="ParkingSegmentID")
    name: TDXName = Field(alias="ParkingSegmentName")
    road_section: dict[str, Any] | None = Field(default=None, alias="RoadSection")
    position: TDXPoint = Field(alias="ParkingSegmentPosition")
    geometry_wkt: str | None = Field(default=None, alias="Geometry")
    description: str | None = Field(default=None, alias="Description")
    fare_description: str | None = Field(default=None, alias="FareDescription")
    has_charging_point: TDXFlag | None = Field(default=None, alias="HasChargingPoint")
    image_urls: list[str] | None = Field(default=None, alias="ImageURLs")
    city: NonEmptyStr = Field(alias="City")
    city_code: NonEmptyStr = Field(alias="CityCode")
    town_name: str | None = Field(default=None, alias="TownName")
    town_id: str | None = Field(default=None, alias="TownID")
    landmark: str | None = Field(default=None, alias="LandMark")
    roads: list[dict[str, Any]] | None = Field(default=None, alias="Roads")
    links: list[dict[str, Any]] | None = Field(default=None, alias="Links")

    @model_validator(mode="after")
    def has_name(self):
        if self.name.primary is None:
            raise ValueError("ParkingSegmentName must contain Zh_tw or En")
        return self


class TDXParkingSegmentResponse(TDXParkingWrapper):
    records: list[TDXParkingSegment] = Field(alias="ParkingSegments")


class TDXOnStreetSpot(TDXModel):
    parking_segment_id: NonEmptyStr = Field(alias="ParkingSegmentID")
    parking_spot_id: NonEmptyStr = Field(alias="ParkingSpotID")
    position: TDXPoint = Field(alias="Position")
    space_type: int = Field(alias="SpaceType")
    has_charging_point: TDXFlag = Field(alias="HasChargingPoint")
    geometry_wkt: str | None = Field(default=None, alias="Geometry")
    length_cm: float | None = Field(default=None, alias="Length")
    width_cm: float | None = Field(default=None, alias="Width")
    link_id: str | None = Field(default=None, alias="LinkID")


class TDXOnStreetSpotResponse(TDXParkingWrapper):
    records: list[TDXOnStreetSpot] = Field(alias="ParkingSegmentSpots")
