from django.contrib import admin
from django.contrib.gis.admin import GISModelAdmin

from .models import (
    ParkingEntrance,
    ParkingLot,
    ParkingSegment,
    ParkingSpot,
    SourceReference,
)


@admin.register(ParkingLot)
class ParkingLotAdmin(GISModelAdmin):
    list_display = ("name", "city_code", "district_name", "is_public", "updated_at")
    list_filter = ("city_code", "is_public", "has_ev_charging", "has_live_occupancy")
    search_fields = ("name", "name_en", "address", "source_references__source_id")
    readonly_fields = ("id", "created_at", "updated_at")


@admin.register(ParkingEntrance)
class ParkingEntranceAdmin(GISModelAdmin):
    list_display = ("name", "access_kind", "lot", "road_name", "updated_at")
    list_filter = ("access_kind", "access_type")
    search_fields = ("name", "road_name", "lot__name", "source_references__source_id")
    list_select_related = ("lot",)
    readonly_fields = ("id", "created_at", "updated_at")


@admin.register(ParkingSegment)
class ParkingSegmentAdmin(GISModelAdmin):
    list_display = ("name", "city_code", "district_name", "has_charging_point", "updated_at")
    list_filter = ("city_code", "has_charging_point")
    search_fields = ("name", "name_en", "description", "source_references__source_id")
    readonly_fields = ("id", "created_at", "updated_at")


@admin.register(ParkingSpot)
class ParkingSpotAdmin(GISModelAdmin):
    list_display = (
        "id",
        "context",
        "vehicle_type",
        "source_space_type",
        "has_charging_point",
        "updated_at",
    )
    list_filter = ("context", "vehicle_type", "has_charging_point")
    search_fields = ("id", "source_references__source_id", "lot__name", "segment__name")
    list_select_related = ("lot", "segment")
    readonly_fields = ("id", "created_at", "updated_at")


@admin.register(SourceReference)
class SourceReferenceAdmin(admin.ModelAdmin):
    list_display = (
        "source",
        "authority_code",
        "dataset",
        "source_id",
        "entity_type",
        "is_active",
        "last_seen_at",
    )
    list_filter = ("source", "authority_code", "dataset", "entity_type", "is_active")
    search_fields = ("source_id", "entity__id")
    list_select_related = ("entity",)
    readonly_fields = ("created_at", "updated_at")
