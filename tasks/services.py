"""
Bridge between Django models and the HealthAwareTaskManager.
"""
import calendar
from datetime import date, datetime, timedelta

from django.db.models import Q
from task_manager import HealthAwareTaskManager


def get_manager_from_settings(settings):
    """Build HealthAwareTaskManager from ScheduleSettings model."""
    # Guard against legacy/misconfigured tiny intervals that flood the day.
    interval = max(30, int(settings.break_interval_minutes or 90))
    return HealthAwareTaskManager(
        work_start_hour=settings.work_start_hour,
        work_end_hour=settings.work_end_hour,
        focus_block_max_hours=settings.focus_block_max_hours,
        break_interval_minutes=interval,
        lunch_duration_minutes=max(15, int(settings.lunch_duration_minutes or 60)),
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


def _as_naive(dt):
    if getattr(dt, "tzinfo", None) is not None:
        return dt.replace(tzinfo=None)
    return dt


def _imported_busy_for_day(user, schedule_date, settings):
    """
    Load imported Google events as busy intervals + display items for one day.
    All-day / multi-day events that overlap the day block the workday window.
    """
    from .models import ImportedCalendarEvent

    if user is None:
        return [], []

    work_start = datetime.combine(schedule_date, datetime.min.time()).replace(
        hour=settings.work_start_hour, minute=0, second=0, microsecond=0
    )
    work_end = datetime.combine(schedule_date, datetime.min.time()).replace(
        hour=settings.work_end_hour, minute=0, second=0, microsecond=0
    )
    day_start = datetime.combine(schedule_date, datetime.min.time())
    day_end = day_start + timedelta(days=1)

    # Pull a small window then filter by real overlap (handles overnight / multi-day).
    candidates = ImportedCalendarEvent.objects.filter(user=user).exclude(status='cancelled').filter(
        schedule_date__gte=schedule_date - timedelta(days=14),
        schedule_date__lte=schedule_date,
    )

    busy_slots = []
    external_items = []
    for event in candidates:
        start = _as_naive(event.start_at)
        end = _as_naive(event.end_at)
        if end <= day_start or start >= day_end:
            continue
        if event.is_all_day:
            start = work_start
            end = work_end
        if end <= work_start or start >= work_end:
            continue
        display_start = max(start, work_start)
        display_end = min(end, work_end)
        if display_end <= display_start:
            continue
        busy_slots.append((display_start, display_end))
        external_items.append({
            'start_time': display_start,
            'end_time': display_end,
            'duration_minutes': int((display_end - display_start).total_seconds() / 60),
            'is_break': False,
            'is_external': True,
            'is_busy': True,
            'task_name': event.summary or 'Google event',
            'task_description': event.description or '',
            'google_event_id': event.google_event_id,
            'task_id': None,
        })
    return busy_slots, external_items


def build_schedule(task_queryset, settings, schedule_date=None, user=None):
    """
    Build scheduled items from Django Task queryset.
    Pass a queryset already scoped to one user (e.g. Task.objects.filter(user=u)).
    Returns list of dicts for templates and health summary dict.

    When user is provided, imported Google Calendar events block busy time and
    appear as locked external cards on the timeline.
    """
    manager = get_manager_from_settings(settings)
    effective_date = schedule_date or date.today()
    if user is None:
        # Infer from queryset when possible (single-user filter).
        try:
            sample = task_queryset.first()
            if sample is not None:
                user = sample.user
        except Exception:
            user = None

    eligible_tasks = task_queryset.filter(completed=False).filter(
        Q(starts_on__isnull=True) | Q(starts_on__lte=effective_date)
    )
    workday_minutes = max(60, (settings.work_end_hour - settings.work_start_hour) * 60)
    for t in eligible_tasks:
        if not _is_task_due_on_date(t, effective_date):
            continue
        remaining = t.remaining_minutes(on_date=effective_date)
        if remaining <= 0:
            continue
        # Don't dump a multi-day total budget into one day — cap to the workday
        # so pinning/dragging a start time can still succeed.
        schedule_minutes = remaining
        if getattr(t, 'duration_mode', 'per_task') == 'total_budget':
            schedule_minutes = min(remaining, workday_minutes)
        manager.add_task(
            name=t.name,
            duration_minutes=schedule_minutes,
            priority=t.priority,
            task_type=t.task_type,
            deadline=t.deadline.isoformat() if t.deadline else None,
            description=t.description or "",
            source_id=t.pk,
            start_time=t.start_time,
            splittable=t.splittable if t.task_type != 'meeting' else False,
        )

    busy_slots, external_items = _imported_busy_for_day(user, effective_date, settings)

    if schedule_date:
        start = datetime.combine(schedule_date, datetime.min.time()).replace(
            hour=settings.work_start_hour, minute=0, second=0, microsecond=0
        )
    else:
        start = None
    manager.schedule_tasks(start_date=start, busy_slots=busy_slots)

    items = []
    for item in manager.scheduled_items:
        d = {
            'start_time': item.start_time,
            'end_time': item.end_time,
            'duration_minutes': int((item.end_time - item.start_time).total_seconds() / 60),
            'is_break': item.is_break,
            'is_external': False,
        }
        if item.is_break and item.break_item:
            d['break_type'] = item.break_item.type
            d['break_description'] = item.break_item.description
        if not item.is_break and item.task:
            d['task_name'] = item.task.name
            d['task_priority'] = item.task.priority.value
            d['task_type'] = item.task.task_type.value
            d['task_description'] = item.task.description or ""
            d['task_id'] = item.task.source_id
            d['task_remaining_minutes'] = item.task.duration_minutes
        items.append(d)

    items.extend(external_items)
    items.sort(key=lambda x: x['start_time'])

    summary = manager.get_health_summary()
    return items, summary
