from django.contrib import admin
from .models import TimeOffConfiguration


@admin.register(TimeOffConfiguration)
class TimeOffConfigurationAdmin(admin.ModelAdmin):
    list_display = ("employer_id", "created_at", "updated_at")
    search_fields = ("employer_id",)
