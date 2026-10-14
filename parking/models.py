import uuid

from django.contrib.gis.db import models
from django.db.models import Q


class EntityKind(models.TextChoices):
    LOT = "lot", "Parking lot"
    ENTRANCE = "entrance", "Parking entrance or exit"
    SEGMENT = "segment", "On-street parking segment"
    SPOT = "spot", "Parking spot"


class SourceProvider(models.TextChoices):
    TDX = "tdx", "TDX"


class SourceDataset(models.TextChoices):
    CAR_PARK = "car_park", "Off-street car park"
    ENTRANCE_EXIT = "entrance_exit", "Off-street entrance and exit"
    OFF_STREET_SPOT = "off_street_spot", "Off-street parking spot"
    PARKING_SEGMENT = "parking_segment", "On-street parking segment"
    ON_STREET_SPOT = "on_street_spot", "On-street parking spot"


class IdentifierKind(models.TextChoices):
    PROVIDED = "provided", "Provided by source"
    DERIVED = "derived", "Deterministically derived"


class VehicleType(models.TextChoices):
    CAR = "car", "Car"
    MOTORCYCLE = "motorcycle", "Motorcycle or scooter"
    HEAVY_MOTORCYCLE = "heavy_motorcycle", "Heavy motorcycle"
    OTHER = "other", "Other or unknown"


class AccessKind(models.TextChoices):
    ENTRANCE = "entrance", "Entrance"
    EXIT = "exit", "Exit"
    ENTRANCE_EXIT = "entrance_exit", "Combined entrance and exit"


class SpotContext(models.TextChoices):
    OFF_STREET = "off_street", "Off-street lot"
    ON_STREET = "on_street", "On-street segment"


class ParkingEntity(models.Model):
    """Stable Blipark identity shared by every parking entity."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    kind = models.CharField(max_length=16, choices=EntityKind.choices, editable=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("kind", "id")

    def __str__(self):
        return f"{self.get_kind_display()} {self.id}"


class TypedParkingEntity(ParkingEntity):
    """Set the discriminator for concrete multi-table subclasses."""

    ENTITY_KIND: str

    class Meta:
        abstract = True

    def save(self, *args, **kwargs):
        self.kind = self.ENTITY_KIND
        return super().save(*args, **kwargs)


class ParkingLot(TypedParkingEntity):
    ENTITY_KIND = EntityKind.LOT

    name = models.CharField(max_length=255)
    name_en = models.CharField(max_length=255, blank=True)
    short_name = models.CharField(max_length=255, blank=True)
    description = models.TextField(blank=True)
    address = models.CharField(max_length=500, blank=True)
    city_code = models.CharField(max_length=16, db_index=True)
    district_id = models.CharField(max_length=32, blank=True)
    district_name = models.CharField(max_length=100, blank=True)
    location = models.PointField(srid=4326)
    boundary = models.GeometryField(srid=4326, null=True, blank=True)
    car_park_type = models.PositiveSmallIntegerField(null=True, blank=True)
    operation_type = models.PositiveSmallIntegerField(null=True, blank=True)
    fare_description = models.TextField(blank=True)
    is_public = models.BooleanField(null=True, blank=True)
    has_live_occupancy = models.BooleanField(null=True, blank=True)
    has_ev_charging = models.BooleanField(null=True, blank=True)
    is_wheelchair_accessible = models.BooleanField(null=True, blank=True)
    allows_overnight = models.BooleanField(null=True, blank=True)

    class Meta:
        indexes = [models.Index(fields=("city_code", "name"), name="lot_city_name_idx")]

    def __str__(self):
        return self.name


class ParkingEntrance(TypedParkingEntity):
    ENTITY_KIND = EntityKind.ENTRANCE

    lot = models.ForeignKey(ParkingLot, on_delete=models.CASCADE, related_name="entrances")
    access_kind = models.CharField(max_length=16, choices=AccessKind.choices)
    name = models.CharField(max_length=255, blank=True)
    location = models.PointField(srid=4326)
    access_type = models.PositiveSmallIntegerField(null=True, blank=True)
    max_height_cm = models.FloatField(null=True, blank=True)
    max_width_cm = models.FloatField(null=True, blank=True)
    max_weight_kg = models.FloatField(null=True, blank=True)
    road_name = models.CharField(max_length=255, blank=True)
    bearing = models.CharField(max_length=8, blank=True)

    class Meta:
        indexes = [models.Index(fields=("lot", "access_kind"), name="entrance_lot_kind_idx")]

    def __str__(self):
        return self.name or f"{self.get_access_kind_display()} — {self.lot}"


class ParkingSegment(TypedParkingEntity):
    ENTITY_KIND = EntityKind.SEGMENT

    name = models.CharField(max_length=255)
    name_en = models.CharField(max_length=255, blank=True)
    description = models.TextField(blank=True)
    fare_description = models.TextField(blank=True)
    city_code = models.CharField(max_length=16, db_index=True)
    district_id = models.CharField(max_length=32, blank=True)
    district_name = models.CharField(max_length=100, blank=True)
    representative_point = models.PointField(srid=4326)
    geometry = models.LineStringField(srid=4326, null=True, blank=True)
    has_charging_point = models.BooleanField(null=True, blank=True)

    class Meta:
        indexes = [models.Index(fields=("city_code", "name"), name="segment_city_name_idx")]

    def __str__(self):
        return self.name


class ParkingSpot(TypedParkingEntity):
    ENTITY_KIND = EntityKind.SPOT

    context = models.CharField(max_length=16, choices=SpotContext.choices)
    lot = models.ForeignKey(
        ParkingLot,
        null=True,
        blank=True,
        on_delete=models.CASCADE,
        related_name="spots",
    )
    segment = models.ForeignKey(
        ParkingSegment,
        null=True,
        blank=True,
        on_delete=models.CASCADE,
        related_name="spots",
    )
    location = models.PointField(srid=4326, null=True, blank=True)
    footprint = models.GeometryField(srid=4326, null=True, blank=True)
    vehicle_type = models.CharField(max_length=24, choices=VehicleType.choices)
    source_space_type = models.PositiveSmallIntegerField()
    has_charging_point = models.BooleanField(default=False)
    floor = models.CharField(max_length=32, blank=True)
    length_cm = models.FloatField(null=True, blank=True)
    width_cm = models.FloatField(null=True, blank=True)

    class Meta:
        constraints = [
            models.CheckConstraint(
                condition=(
                    Q(
                        context=SpotContext.OFF_STREET,
                        lot__isnull=False,
                        segment__isnull=True,
                    )
                    | Q(
                        context=SpotContext.ON_STREET,
                        lot__isnull=True,
                        segment__isnull=False,
                        location__isnull=False,
                    )
                ),
                name="spot_context_parent_ck",
            )
        ]
        indexes = [
            models.Index(fields=("context", "vehicle_type"), name="spot_context_vehicle_idx")
        ]

    def __str__(self):
        return f"{self.get_context_display()} {self.id}"


class SourceReference(models.Model):
    """Provenance and idempotency key kept separate from the domain identity."""

    entity = models.ForeignKey(
        ParkingEntity,
        on_delete=models.CASCADE,
        related_name="source_references",
    )
    entity_type = models.CharField(max_length=16, choices=EntityKind.choices)
    source = models.CharField(max_length=16, choices=SourceProvider.choices)
    dataset = models.CharField(max_length=32, choices=SourceDataset.choices)
    authority_code = models.CharField(max_length=32)
    source_id = models.CharField(max_length=255)
    identifier_kind = models.CharField(
        max_length=16,
        choices=IdentifierKind.choices,
        default=IdentifierKind.PROVIDED,
    )
    source_updated_at = models.DateTimeField(null=True, blank=True)
    last_seen_at = models.DateTimeField()
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=("source", "authority_code", "dataset", "source_id"),
                name="source_ref_identity_uniq",
            ),
            models.UniqueConstraint(
                fields=("entity", "source", "authority_code", "dataset"),
                name="source_ref_entity_dataset_uniq",
            ),
        ]
        indexes = [
            models.Index(
                fields=("source", "authority_code", "dataset", "is_active"),
                name="source_ref_active_idx",
            ),
            models.Index(fields=("last_seen_at",), name="source_ref_seen_idx"),
        ]

    def __str__(self):
        return f"{self.source}:{self.authority_code}:{self.dataset}:{self.source_id}"
