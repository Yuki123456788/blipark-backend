from django.contrib import admin, messages
from django.contrib.gis.admin import GISModelAdmin
from django.core.exceptions import PermissionDenied
from django.http import HttpResponseRedirect
from django.template.response import TemplateResponse
from django.urls import path, reverse

from integrations.tdx.client import TDXClientError
from integrations.tdx.runner import run_tdx_sync

from .admin_inspection import build_data_inspection_context
from .models import (
    ParkingEntrance,
    ParkingLot,
    ParkingSegment,
    ParkingSpot,
    SourceReference,
    SyncDatasetResult,
    SyncIssue,
    SyncRun,
    SyncStatus,
    SyncTrigger,
)
from .sync_lock import SyncAlreadyRunningError, single_sync_run


@admin.register(ParkingLot)
class ParkingLotAdmin(GISModelAdmin):
    change_list_template = "admin/parking/parkinglot/change_list.html"
    list_display = ("name", "city_code", "district_name", "is_public", "updated_at")
    list_filter = ("city_code", "is_public", "has_ev_charging", "has_live_occupancy")
    search_fields = ("name", "name_en", "address", "source_references__source_id")
    readonly_fields = ("id", "created_at", "updated_at")

    def get_urls(self):
        inspection_url = path(
            "data-inspection/",
            self.admin_site.admin_view(self.data_inspection_view),
            name="parking_data_inspection",
        )
        return [inspection_url, *super().get_urls()]

    def data_inspection_view(self, request):
        context = {
            **self.admin_site.each_context(request),
            **build_data_inspection_context(),
            "opts": self.model._meta,
            "title": "Parking data inspection",
        }
        return TemplateResponse(request, "admin/parking/data_inspection.html", context)


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
        "pages_fetched",
        "fetched",
        "valid",
        "invalid",
        "mapped",
        "inserted",
        "updated",
        "unchanged",
        "failed",
    )
    readonly_fields = fields


@admin.register(SyncRun)
class SyncRunAdmin(admin.ModelAdmin):
    change_list_template = "admin/parking/syncrun/change_list.html"
    list_display = ("id", "source", "city", "status", "started_at", "finished_at")
    list_filter = ("source", "city", "status", "trigger")
    search_fields = ("id", "authority_code", "error_summary")
    readonly_fields = ("id", "started_at", "finished_at")
    inlines = (SyncDatasetResultInline,)

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False

    def get_urls(self):
        trigger_url = path(
            "trigger/",
            self.admin_site.admin_view(self.trigger_sync_view),
            name="parking_syncrun_trigger",
        )
        return [trigger_url, *super().get_urls()]

    def trigger_sync_view(self, request):
        if not request.user.has_perm("parking.add_syncrun"):
            raise PermissionDenied("User cannot trigger parking sync runs")

        if request.method == "POST":
            try:
                with single_sync_run(source="tdx", city="Tainan"):
                    summary = run_tdx_sync(trigger=SyncTrigger.MANUAL_ADMIN)
            except SyncAlreadyRunningError as error:
                self.message_user(request, str(error), level=messages.WARNING)
                return HttpResponseRedirect(reverse("admin:parking_syncrun_changelist"))
            except TDXClientError as error:
                self.message_user(request, str(error), level=messages.ERROR)
                return HttpResponseRedirect(reverse("admin:parking_syncrun_changelist"))

            level = messages.SUCCESS if summary.status == SyncStatus.SUCCEEDED else messages.WARNING
            self.message_user(
                request,
                f"TDX sync finished with status {summary.status}.",
                level=level,
            )
            return HttpResponseRedirect(
                reverse("admin:parking_syncrun_change", args=(summary.run_id,))
            )

        context = {
            **self.admin_site.each_context(request),
            "opts": self.model._meta,
            "title": "Sync Tainan now",
            "running_sync": SyncRun.objects.filter(status=SyncStatus.RUNNING).first(),
        }
        return TemplateResponse(request, "admin/parking/syncrun/trigger.html", context)


@admin.register(SyncDatasetResult)
class SyncDatasetResultAdmin(admin.ModelAdmin):
    list_display = (
        "run",
        "dataset",
        "status",
        "pages_fetched",
        "fetched",
        "valid",
        "invalid",
        "mapped",
        "inserted",
        "updated",
        "unchanged",
        "failed",
    )
    list_filter = ("dataset", "status")
    search_fields = ("run__id", "error_summary")
    list_select_related = ("run",)
    readonly_fields = ("started_at", "finished_at")


@admin.register(SyncIssue)
class SyncIssueAdmin(admin.ModelAdmin):
    list_display = ("dataset_result", "stage", "code", "source_id", "record_index")
    list_filter = ("stage", "code", "dataset_result__dataset")
    search_fields = ("source_id", "summary", "dataset_result__run__id")
    list_select_related = ("dataset_result", "dataset_result__run")
    readonly_fields = ("created_at",)
