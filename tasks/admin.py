from django.contrib import admin
from .models import Task, ScheduleSettings, WhatsAppNotificationState


@admin.register(Task)
class TaskAdmin(admin.ModelAdmin):
    list_display = [
        'name', 'user', 'duration_minutes', 'priority', 'task_type',
        'schedule_type', 'recurrence_unit', 'recurrence_every',
        'starts_on', 'deadline', 'completed', 'created_at',
    ]
    list_filter = [
        'priority', 'task_type', 'schedule_type', 'recurrence_unit',
        'completed', 'user', 'starts_on',
    ]


@admin.register(ScheduleSettings)
class ScheduleSettingsAdmin(admin.ModelAdmin):
    list_display = ['user', 'work_start_hour', 'work_end_hour', 'break_interval_minutes', 'lunch_hour']


@admin.register(WhatsAppNotificationState)
class WhatsAppNotificationStateAdmin(admin.ModelAdmin):
    list_display = ['user', 'last_event_key', 'last_sent_at', 'last_mqtt_ok', 'last_mqtt_checked_at']
