"""
Bridge between Django models and the HealthAwareTaskManager.
"""
from datetime import datetime
from task_manager import HealthAwareTaskManager


def get_manager_from_settings(settings):
    """Build HealthAwareTaskManager from ScheduleSettings model."""
    return HealthAwareTaskManager(
        work_start_hour=settings.work_start_hour,
        work_end_hour=settings.work_end_hour,
        focus_block_max_hours=settings.focus_block_max_hours,
        break_interval_minutes=settings.break_interval_minutes,
        lunch_duration_minutes=settings.lunch_duration_minutes,
        lunch_hour=settings.lunch_hour,
    )


def build_schedule(task_queryset, settings, schedule_date=None):
    """
    Build scheduled items from Django Task queryset.
    Returns list of dicts for templates and health summary dict.
    """
    manager = get_manager_from_settings(settings)
    for t in task_queryset.filter(completed=False):
        manager.add_task(
            name=t.name,
            duration_minutes=t.duration_minutes,
            priority=t.priority,
            task_type=t.task_type,
            deadline=t.deadline.isoformat() if t.deadline else None,
            description=t.description or "",
        )
    if schedule_date:
        start = datetime.combine(schedule_date, datetime.min.time()).replace(
            hour=settings.work_start_hour, minute=0, second=0, microsecond=0
        )
    else:
        start = None
    manager.schedule_tasks(start_date=start)

    items = []
    for item in manager.scheduled_items:
        d = {
            'start_time': item.start_time,
            'end_time': item.end_time,
            'duration_minutes': int((item.end_time - item.start_time).total_seconds() / 60),
            'is_break': item.is_break,
        }
        if item.is_break and item.break_item:
            d['break_type'] = item.break_item.type
            d['break_description'] = item.break_item.description
        if not item.is_break and item.task:
            d['task_name'] = item.task.name
            d['task_priority'] = item.task.priority.value
            d['task_type'] = item.task.task_type.value
            d['task_description'] = item.task.description or ""
        items.append(d)

    summary = manager.get_health_summary()
    return items, summary
