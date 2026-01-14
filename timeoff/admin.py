from django.contrib import admin
from .models import TimeOffConfiguration, TimeOffType


@admin.register(TimeOffConfiguration)
class TimeOffConfigurationAdmin(admin.ModelAdmin):
    list_display = ("employer_id", "created_at", "updated_at")
    search_fields = ("employer_id",)


@admin.register(TimeOffType)
class TimeOffTypeAdmin(admin.ModelAdmin):
    list_display = ("code", "name", "employer_id", "paid")
    search_fields = ("code", "name", "employer_id")
