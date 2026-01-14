from django.contrib import admin

from .models import FrontdeskStation, StationResponsible, Visitor, Visit


@admin.register(FrontdeskStation)
class FrontdeskStationAdmin(admin.ModelAdmin):
    list_display = ("name", "branch", "is_active", "allow_self_check_in", "created_at")
    list_filter = ("is_active", "allow_self_check_in", "branch")
    search_fields = ("name", "branch__name", "branch__code")


@admin.register(StationResponsible)
class StationResponsibleAdmin(admin.ModelAdmin):
    list_display = ("station", "employee", "created_at")
    search_fields = ("station__name", "employee__first_name", "employee__last_name")


@admin.register(Visitor)
class VisitorAdmin(admin.ModelAdmin):
    list_display = ("full_name", "phone", "email", "organization", "created_at")
    search_fields = ("full_name", "phone", "email", "organization")


@admin.register(Visit)
class VisitAdmin(admin.ModelAdmin):
    list_display = (
        "visitor",
        "host",
        "branch",
        "station",
        "visit_type",
        "status",
        "check_in_time",
        "check_out_time",
    )
    list_filter = ("visit_type", "status", "branch", "station")
    search_fields = ("visitor__full_name", "host__first_name", "host__last_name", "visit_purpose")
