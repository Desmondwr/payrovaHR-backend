from django.contrib import admin

from .models import (
    AttendanceAllowedWifi,
    AttendanceConfiguration,
    AttendanceLocationSite,
    AttendanceRecord,
    WorkingSchedule,
    WorkingScheduleDay,
)

admin.site.register(AttendanceConfiguration)
admin.site.register(AttendanceLocationSite)
admin.site.register(AttendanceAllowedWifi)
admin.site.register(WorkingSchedule)
admin.site.register(WorkingScheduleDay)
admin.site.register(AttendanceRecord)
