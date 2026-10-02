"""TDX-specific processor registry injected into the application sync service."""

from parking.models import SourceDataset
from parking.services.sync import DatasetProcessor

from .client import TDXDataset
from .mapper import (
    TDXMappingError,
    map_car_park,
    map_off_street_spots,
    map_on_street_spot,
    map_parking_entrances,
    map_parking_segment,
)
from .schemas import (
    TDXCarPark,
    TDXOffStreetSpotGroup,
    TDXOnStreetSpot,
    TDXParkingEntranceExit,
    TDXParkingSegment,
)

TDX_PROCESSORS = (
    DatasetProcessor(
        TDXDataset.CAR_PARKS,
        SourceDataset.CAR_PARK,
        TDXCarPark,
        lambda record, metadata: [map_car_park(record, metadata)],
        ("CarParkID",),
        mapping_error_types=(TDXMappingError,),
        authority_by_city={"Tainan": "TNN"},
    ),
    DatasetProcessor(
        TDXDataset.PARKING_ENTRANCE_EXITS,
        SourceDataset.ENTRANCE_EXIT,
        TDXParkingEntranceExit,
        map_parking_entrances,
        ("CarParkID",),
        dependencies=(TDXDataset.CAR_PARKS,),
        mapping_error_types=(TDXMappingError,),
        authority_by_city={"Tainan": "TNN"},
    ),
    DatasetProcessor(
        TDXDataset.OFF_STREET_SPOTS,
        SourceDataset.OFF_STREET_SPOT,
        TDXOffStreetSpotGroup,
        map_off_street_spots,
        ("CarParkID",),
        dependencies=(TDXDataset.CAR_PARKS,),
        mapping_error_types=(TDXMappingError,),
        authority_by_city={"Tainan": "TNN"},
    ),
    DatasetProcessor(
        TDXDataset.PARKING_SEGMENTS,
        SourceDataset.PARKING_SEGMENT,
        TDXParkingSegment,
        lambda record, metadata: [map_parking_segment(record, metadata)],
        ("ParkingSegmentID",),
        mapping_error_types=(TDXMappingError,),
        authority_by_city={"Tainan": "TNN"},
    ),
    DatasetProcessor(
        TDXDataset.ON_STREET_SPOTS,
        SourceDataset.ON_STREET_SPOT,
        TDXOnStreetSpot,
        lambda record, metadata: [map_on_street_spot(record, metadata)],
        ("ParkingSpotID", "ParkingSegmentID"),
        dependencies=(TDXDataset.PARKING_SEGMENTS,),
        mapping_error_types=(TDXMappingError,),
        authority_by_city={"Tainan": "TNN"},
    ),
)
