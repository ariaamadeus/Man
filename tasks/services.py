"""
Bridge between Django models and the HealthAwareTaskManager.
"""
import calendar
from datetime import date, datetime

from django.db.models import Q
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


def _last_day_of_month(year, month):
    return calendar.monthrange(year, month)[1]


def _is_task_due_on_date(task, effective_date):
    if task.schedule_type != 'recurring':
        return True

    every = task.recurrence_every
    unit = task.recurrence_unit
    if not every or every < 1 or not unit:
        return False

    base_date = task.starts_on or task.created_at.date()
    if effective_date < base_date:
        return False

    if unit == 'daily':
        day_delta = (effective_date - base_date).days
        return day_delta % every == 0

    if unit == 'weekly':
        day_delta = (effective_date - base_date).days
        week_delta = day_delta // 7
        return effective_date.weekday() == base_date.weekday() and week_delta % every == 0

    if unit == 'monthly':
        month_delta = ((effective_date.year - base_date.year) * 12) + (effective_date.month - base_date.month)
        if month_delta < 0 or month_delta % every != 0:
            return False
        due_day = min(base_date.day, _last_day_of_month(effective_date.year, effective_date.month))
        return effective_date.day == due_day

    if unit == 'yearly':
        year_delta = effective_date.year - base_date.year
        if year_delta < 0 or year_delta % every != 0:
            return False
        if base_date.month == 2 and base_date.day == 29:
            due_day = min(29, _last_day_of_month(effective_date.year, 2))
            return effective_date.month == 2 and effective_date.day == due_day
        return effective_date.month == base_date.month and effective_date.day == base_date.day

    return False


def build_schedule(task_queryset, settings, schedule_date=None):
    """
    Build scheduled items from Django Task queryset.
    Pass a queryset already scoped to one user (e.g. Task.objects.filter(user=u)).
    Returns list of dicts for templates and health summary dict.
    """
    manager = get_manager_from_settings(settings)
    effective_date = schedule_date or date.today()
    eligible_tasks = task_queryset.filter(completed=False).filter(
        Q(starts_on__isnull=True) | Q(starts_on__lte=effective_date)
    )
    for t in eligible_tasks:
        if not _is_task_due_on_date(t, effective_date):
            continue
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
