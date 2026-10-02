from django.contrib import admin
from django.contrib.gis.admin import GISModelAdmin

from .models import (
    ParkingEntrance,
    ParkingLot,
    ParkingSegment,
    ParkingSpot,
    SourceReference,
    SyncDatasetResult,
    SyncIssue,
    SyncRun,
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
        "source_scope",
        "source_id",
        "source_discriminator",
        "entity_type",
        "is_active",
        "last_seen_at",
    )
    list_filter = ("source", "authority_code", "dataset", "entity_type", "is_active")
    search_fields = ("source_scope", "source_id", "source_discriminator", "entity__id")
    list_select_related = ("entity",)
    readonly_fields = ("created_at", "updated_at")


class SyncDatasetResultInline(admin.TabularInline):
    model = SyncDatasetResult
    extra = 0
    can_delete = False
    show_change_link = True
    fields = (
        "dataset",
        "status",
        "fetched",
        "valid",
        "invalid",
        "inserted",
        "updated",
        "unchanged",
        "failed",
    )
    readonly_fields = fields


@admin.register(SyncRun)
class SyncRunAdmin(admin.ModelAdmin):
    list_display = ("id", "source", "city", "status", "started_at", "finished_at")
    list_filter = ("source", "city", "status", "trigger")
    search_fields = ("id", "authority_code", "error_summary")
    readonly_fields = ("id", "started_at", "finished_at")
    inlines = (SyncDatasetResultInline,)


@admin.register(SyncDatasetResult)
class SyncDatasetResultAdmin(admin.ModelAdmin):
    list_display = (
        "run",
        "dataset",
        "status",
        "fetched",
        "valid",
        "invalid",
        "inserted",
        "updated",
        "unchanged",
        "failed",
    )
    list_filter = ("dataset", "status")
    search_fields = ("run__id", "error_summary")
    list_select_related = ("run",)


@admin.register(SyncIssue)
class SyncIssueAdmin(admin.ModelAdmin):
    list_display = ("dataset_result", "stage", "code", "source_id", "record_index")
    list_filter = ("stage", "code", "dataset_result__dataset")
    search_fields = ("source_id", "summary", "dataset_result__run__id")
    list_select_related = ("dataset_result", "dataset_result__run")
    readonly_fields = ("created_at",)
