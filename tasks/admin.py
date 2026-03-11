from django.contrib import admin
from .models import Task, ScheduleSettings


@admin.register(Task)
class TaskAdmin(admin.ModelAdmin):
    list_display = ['name', 'duration_minutes', 'priority', 'task_type', 'completed', 'created_at']
    list_filter = ['priority', 'task_type', 'completed']


@admin.register(ScheduleSettings)
class ScheduleSettingsAdmin(admin.ModelAdmin):
    list_display = ['work_start_hour', 'work_end_hour', 'break_interval_minutes', 'lunch_hour']
