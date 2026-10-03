"""Read-only aggregates used by the Phase 1 Admin inspection page."""

from django.db.models import Count, Q

from .models import (
    ParkingEntrance,
    ParkingLot,
    ParkingSegment,
    ParkingSpot,
    SourceDataset,
    SourceReference,
    SpotContext,
    SyncRun,
    VehicleType,
)


def build_data_inspection_context() -> dict:
    lot_count = ParkingLot.objects.count()
    segment_count = ParkingSegment.objects.count()
    off_street_count = ParkingSpot.objects.filter(context=SpotContext.OFF_STREET).count()
    on_street_count = ParkingSpot.objects.filter(context=SpotContext.ON_STREET).count()

    source_coverage = SourceReference.objects.values("dataset").annotate(
        total=Count("id"),
        active=Count("id", filter=Q(is_active=True)),
        inactive=Count("id", filter=Q(is_active=False)),
    )
    vehicle_coverage = ParkingSpot.objects.values("context", "vehicle_type").annotate(
        total=Count("id")
    )

    return {
        "entity_counts": (
            ("Parking lots", lot_count),
            ("Entrances and exits", ParkingEntrance.objects.count()),
            ("Parking segments", segment_count),
            ("Off-street spots", off_street_count),
            ("On-street spots", on_street_count),
        ),
        "relationship_coverage": (
            (
                "Lots with an entrance or exit",
                ParkingLot.objects.filter(entrances__isnull=False).distinct().count(),
                lot_count,
            ),
            (
                "Lots with a parking spot",
                ParkingLot.objects.filter(spots__isnull=False).distinct().count(),
                lot_count,
            ),
            (
                "Segments with a parking spot",
                ParkingSegment.objects.filter(spots__isnull=False).distinct().count(),
                segment_count,
            ),
        ),
        "geometry_gaps": (
            (
                "Lots without a boundary",
                ParkingLot.objects.filter(boundary__isnull=True).count(),
                lot_count,
            ),
            (
                "Segments without a line geometry",
                ParkingSegment.objects.filter(geometry__isnull=True).count(),
                segment_count,
            ),
            (
                "Off-street spots without a location",
                ParkingSpot.objects.filter(
                    context=SpotContext.OFF_STREET,
                    location__isnull=True,
                ).count(),
                off_street_count,
            ),
        ),
        "source_coverage": tuple(
            {
                **row,
                "dataset_label": SourceDataset(row["dataset"]).label,
            }
            for row in source_coverage.order_by("dataset")
        ),
        "vehicle_coverage": tuple(
            {
                **row,
                "context_label": SpotContext(row["context"]).label,
                "vehicle_label": VehicleType(row["vehicle_type"]).label,
            }
            for row in vehicle_coverage.order_by("context", "vehicle_type")
        ),
        "latest_run": SyncRun.objects.prefetch_related("dataset_results").first(),
    }
