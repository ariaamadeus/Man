"""
Deterministic schedule readjust hooks.

v1: when Google busy time changes, unpin local tasks that collide.
v2 (later): AI can allocate total_budget session chunks into free gaps.
"""
from __future__ import annotations

import logging
from datetime import date, datetime, timedelta

from .models import ImportedCalendarEvent, Task

logger = logging.getLogger(__name__)


def on_constraints_changed(user, dates: list[date], reason: str = "google_pull") -> dict:
    """
    React to new constraints (e.g. Google Calendar pull).

    Returns counts of adjustments made.
    """
    if not dates:
        return {"unpinned": 0}

    unpinned = 0
    for day in dates:
        unpinned += _unpin_overlapping_tasks(user, day)

    if unpinned:
        logger.info(
            "schedule_adjust reason=%s user=%s unpinned=%s dates=%s",
            reason,
            getattr(user, "pk", user),
            unpinned,
            [d.isoformat() for d in dates],
        )
    return {"unpinned": unpinned}


def _as_naive(dt: datetime) -> datetime:
    if getattr(dt, "tzinfo", None) is not None:
        return dt.replace(tzinfo=None)
    return dt


def _unpin_overlapping_tasks(user, day: date) -> int:
    """Clear start_time when a pinned local task overlaps Google busy time."""
    busy = list(
        ImportedCalendarEvent.objects.filter(
            user=user,
            schedule_date=day,
        ).exclude(status="cancelled")
    )
    if not busy:
        return 0

    count = 0
    pinned = Task.objects.filter(user=user, completed=False, start_time__isnull=False)
    for task in pinned:
        start = datetime.combine(day, task.start_time)
        end = start + timedelta(minutes=max(1, task.remaining_minutes(on_date=day)))
        for event in busy:
            ev_start = _as_naive(event.start_at)
            ev_end = _as_naive(event.end_at)
            if start < ev_end and end > ev_start:
                task.start_time = None
                task.save(update_fields=["start_time"])
                count += 1
                break
    return count
