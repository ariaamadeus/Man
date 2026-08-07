from django.contrib import admin
from .models import (
    Task,
    ScheduleSettings,
    WhatsAppNotificationState,
    GoogleCalendarConnection,
    CalendarEventMapping,
)


@admin.register(Task)
class TaskAdmin(admin.ModelAdmin):
    list_display = [
        'name', 'user', 'duration_minutes', 'priority', 'task_type',
        'schedule_type', 'recurrence_unit', 'recurrence_every',
        'starts_on', 'start_time', 'splittable', 'deadline', 'completed', 'created_at',
    ]
    list_filter = [
        'priority', 'task_type', 'schedule_type', 'recurrence_unit',
        'splittable', 'completed', 'user', 'starts_on',
    ]


@admin.register(ScheduleSettings)
class ScheduleSettingsAdmin(admin.ModelAdmin):
    list_display = ['user', 'work_start_hour', 'work_end_hour', 'break_interval_minutes', 'lunch_hour']


@admin.register(WhatsAppNotificationState)
class WhatsAppNotificationStateAdmin(admin.ModelAdmin):
    list_display = ['user', 'last_event_key', 'last_sent_at', 'last_mqtt_ok', 'last_mqtt_checked_at']


@admin.register(GoogleCalendarConnection)
class GoogleCalendarConnectionAdmin(admin.ModelAdmin):
    list_display = [
        'user', 'calendar_id', 'sync_enabled', 'sync_breaks',
        'last_sync_ok', 'last_synced_at', 'connected_at',
    ]
    list_filter = ['sync_enabled', 'last_sync_ok']
    readonly_fields = ['token_json', 'last_sync_error', 'connected_at', 'updated_at']


@admin.register(CalendarEventMapping)
class CalendarEventMappingAdmin(admin.ModelAdmin):
    list_display = ['user', 'schedule_date', 'local_key', 'google_event_id', 'updated_at']
    list_filter = ['schedule_date', 'user']
    search_fields = ['local_key', 'google_event_id']
