"""
Health-Aware Task Manager
A task management system that schedules your work tasks while prioritizing your health.
"""

import sys
import os

from datetime import datetime, timedelta, time
from typing import List, Dict, Optional
from dataclasses import dataclass, field
from enum import Enum
import json


class TaskPriority(Enum):
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


class TaskType(Enum):
    FOCUS = "focus"  # Deep work requiring concentration
    MEETING = "meeting"
    ADMIN = "admin"  # Administrative tasks
    CREATIVE = "creative"
    LEARNING = "learning"


@dataclass
class Task:
    name: str
    duration_minutes: int
    priority: TaskPriority
    task_type: TaskType
    deadline: Optional[str] = None
    description: str = ""
    completed: bool = False
    source_id: Optional[int] = None  # Django Task.pk when bridged from the web app
    start_time: Optional[time] = None  # Preferred clock time for scheduling
    splittable: bool = True  # False for meetings / contiguous blocks


@dataclass
class HealthBreak:
    type: str  # "physical", "mental", "hydration", "meal"
    duration_minutes: int
    description: str
    scheduled_time: Optional[datetime] = None


@dataclass
class ScheduledItem:
    start_time: datetime
    end_time: datetime
    task: Optional[Task] = None
    break_item: Optional[HealthBreak] = None
    is_break: bool = False


class HealthAwareTaskManager:
    """
    Manages tasks with health considerations:
    - Regular breaks for physical movement
    - Mental health breaks
    - Hydration reminders
    - Meal times
    - Prevents overloading
    - Respects work-life balance
    """
    
    def __init__(
        self,
        work_start_hour: int = 9,
        work_end_hour: int = 17,
        focus_block_max_hours: float = 2.0,
        break_interval_minutes: int = 90,
        lunch_duration_minutes: int = 60,
        lunch_hour: int = 13
    ):
        self.work_start_hour = work_start_hour
        self.work_end_hour = work_end_hour
        self.focus_block_max_hours = focus_block_max_hours
        self.break_interval_minutes = break_interval_minutes
        self.lunch_duration_minutes = lunch_duration_minutes
        self.lunch_hour = lunch_hour
        
        self.tasks: List[Task] = []
        self.scheduled_items: List[ScheduledItem] = []
        
    def add_task(
        self,
        name: str,
        duration_minutes: int,
        priority: str = "medium",
        task_type: str = "focus",
        deadline: Optional[str] = None,
        description: str = "",
        source_id: Optional[int] = None,
        start_time: Optional[time] = None,
        splittable: Optional[bool] = None,
    ):
        """Add a new task to the manager."""
        resolved_type = TaskType(task_type.lower())
        # Meetings are always unsplittable unless explicitly overridden.
        if splittable is None:
            splittable = resolved_type != TaskType.MEETING
        elif resolved_type == TaskType.MEETING:
            splittable = False
        task = Task(
            name=name,
            duration_minutes=duration_minutes,
            priority=TaskPriority(priority.lower()),
            task_type=resolved_type,
            deadline=deadline,
            description=description,
            source_id=source_id,
            start_time=start_time,
            splittable=splittable,
        )
        self.tasks.append(task)
        return task
    
    def _create_health_breaks(self, start_time: datetime, end_time: datetime) -> List[HealthBreak]:
        """Generate health breaks between start and end time.

        ``break_interval_minutes`` is the focused work time *between* breaks.
        Breaks never overlap each other; the next one starts only after the
        previous break ends plus the work interval.
        """
        breaks: List[HealthBreak] = []

        # Clamp so a tiny/misconfigured interval cannot flood the day.
        physical_mins = 10
        mental_mins = 15
        work_interval = max(30, int(self.break_interval_minutes or 90))

        # Lunch break
        lunch_time = start_time.replace(hour=self.lunch_hour, minute=0, second=0, microsecond=0)
        lunch_duration = max(15, int(self.lunch_duration_minutes or 60))
        if start_time <= lunch_time < end_time:
            breaks.append(HealthBreak(
                type="meal",
                duration_minutes=lunch_duration,
                description="Lunch break - Step away from your desk, eat mindfully",
                scheduled_time=lunch_time,
            ))

        def overlaps_existing(start: datetime, duration: int) -> bool:
            end = start + timedelta(minutes=duration)
            for br in breaks:
                if not br.scheduled_time:
                    continue
                br_end = br.scheduled_time + timedelta(minutes=br.duration_minutes)
                if start < br_end and end > br.scheduled_time:
                    return True
            return False

        # Regular breaks: work_interval of focus, then a short break, repeat.
        cursor = start_time
        regular_count = 0
        while True:
            next_break_time = cursor + timedelta(minutes=work_interval)
            # Prefer mental every 3rd regular break.
            if regular_count > 0 and regular_count % 3 == 2:
                break_type = "mental"
                break_desc = "Mental break - Deep breathing, meditation, or just rest (10-15 min)"
                duration = mental_mins
            else:
                break_type = "physical"
                break_desc = "Physical break - Stand up, stretch, walk around (5-10 min)"
                duration = physical_mins

            if next_break_time + timedelta(minutes=duration) > end_time:
                break

            # Push past lunch (or any already-placed break) if we would collide.
            while overlaps_existing(next_break_time, duration):
                conflict_end = next_break_time
                for br in breaks:
                    if not br.scheduled_time:
                        continue
                    br_end = br.scheduled_time + timedelta(minutes=br.duration_minutes)
                    proposed_end = next_break_time + timedelta(minutes=duration)
                    if next_break_time < br_end and proposed_end > br.scheduled_time:
                        conflict_end = max(conflict_end, br_end)
                if conflict_end == next_break_time:
                    break
                # Resume focus after the conflicting break, then take another interval.
                next_break_time = conflict_end + timedelta(minutes=work_interval)
                if next_break_time + timedelta(minutes=duration) > end_time:
                    next_break_time = None
                    break

            if next_break_time is None:
                break

            breaks.append(HealthBreak(
                type=break_type,
                duration_minutes=duration,
                description=break_desc,
                scheduled_time=next_break_time,
            ))
            regular_count += 1
            # Next focus block starts when this break ends.
            cursor = next_break_time + timedelta(minutes=duration)

        # Hydration reminders (every 60 minutes, not during / near other breaks)
        hydration_time = start_time
        while hydration_time < end_time:
            hydration_time += timedelta(minutes=60)
            if hydration_time >= end_time:
                break
            too_close = False
            for br in breaks:
                if not br.scheduled_time:
                    continue
                br_end = br.scheduled_time + timedelta(minutes=br.duration_minutes)
                # Skip if inside a break or within 5 minutes of one.
                if br.scheduled_time - timedelta(minutes=5) <= hydration_time <= br_end + timedelta(minutes=5):
                    too_close = True
                    break
            if not too_close:
                breaks.append(HealthBreak(
                    type="hydration",
                    duration_minutes=1,
                    description="💧 Hydration reminder - Drink water!",
                    scheduled_time=hydration_time,
                ))

        return sorted(breaks, key=lambda x: x.scheduled_time if x.scheduled_time else datetime.max)
    
    def schedule_tasks(self, start_date: Optional[datetime] = None) -> List[ScheduledItem]:
        """
        Schedule all tasks with health breaks integrated.
        Tasks with a start_time are pinned to that clock time and scheduled first.
        Meetings / unsplittable tasks are never split around breaks.
        """
        if not self.tasks:
            return []

        if start_date is None:
            start_date = datetime.now().replace(hour=self.work_start_hour, minute=0, second=0, microsecond=0)
            if start_date < datetime.now():
                start_date = start_date + timedelta(days=1)

        work_end = start_date.replace(hour=self.work_end_hour, minute=0, second=0, microsecond=0)
        health_breaks = self._create_health_breaks(start_date, work_end)

        pinned_tasks = sorted(
            [t for t in self.tasks if not t.completed and t.start_time is not None],
            key=lambda t: t.start_time or time.max,
        )
        flexible_tasks = sorted(
            [t for t in self.tasks if not t.completed and t.start_time is None],
            key=lambda t: (
                0 if t.priority == TaskPriority.HIGH else (1 if t.priority == TaskPriority.MEDIUM else 2),
                t.deadline if t.deadline else "9999-12-31",
                t.duration_minutes,
            ),
        )

        # Occupied intervals: (start, end) — pinned tasks + placed breaks that must stay
        occupied: List[tuple] = []
        scheduled_items: List[ScheduledItem] = []

        def overlaps(start: datetime, end: datetime) -> bool:
            for occ_start, occ_end in occupied:
                if start < occ_end and end > occ_start:
                    return True
            return False

        def reserve(start: datetime, end: datetime):
            occupied.append((start, end))
            occupied.sort(key=lambda x: x[0])

        def next_free_cursor(cursor: datetime, duration: timedelta) -> Optional[datetime]:
            """Find the earliest time >= cursor where [time, time+duration) is free and within work hours."""
            t = cursor
            if t < start_date:
                t = start_date
            while t + duration <= work_end:
                end = t + duration
                conflict = None
                for occ_start, occ_end in occupied:
                    if t < occ_end and end > occ_start:
                        conflict = occ_end
                        break
                if conflict is None:
                    return t
                t = conflict
            return None

        # --- Pass 1: pin fixed-start tasks ---
        for task in pinned_tasks:
            preferred = start_date.replace(
                hour=task.start_time.hour,
                minute=task.start_time.minute,
                second=0,
                microsecond=0,
            )
            if preferred < start_date:
                preferred = start_date
            if preferred >= work_end:
                continue

            # Place as much as fits from the pin; leftover stays for pass 3.
            wanted = task.duration_minutes
            max_mins = int((work_end - preferred).total_seconds() / 60)
            place_mins = min(wanted, max_mins)
            if place_mins < 1:
                continue
            duration = timedelta(minutes=place_mins)

            if overlaps(preferred, preferred + duration):
                # Shrink to the free gap at preferred, or find next free slot.
                gap_end = work_end
                for occ_start, occ_end in occupied:
                    if occ_start > preferred:
                        gap_end = min(gap_end, occ_start)
                        break
                    if occ_start <= preferred < occ_end:
                        preferred = occ_end
                        gap_end = work_end
                        for occ2_s, occ2_e in occupied:
                            if occ2_s > preferred:
                                gap_end = min(gap_end, occ2_s)
                                break
                        break
                if preferred >= work_end:
                    continue
                place_mins = min(wanted, int((gap_end - preferred).total_seconds() / 60))
                if place_mins < 1:
                    alt = next_free_cursor(preferred, timedelta(minutes=min(wanted, 15)))
                    if alt is None:
                        continue
                    preferred = alt
                    place_mins = min(
                        wanted,
                        int((work_end - preferred).total_seconds() / 60),
                    )
                    for occ_start, occ_end in occupied:
                        if occ_start > preferred:
                            place_mins = min(
                                place_mins,
                                int((occ_start - preferred).total_seconds() / 60),
                            )
                            break
                duration = timedelta(minutes=max(1, place_mins))

            scheduled_items.append(ScheduledItem(
                start_time=preferred,
                end_time=preferred + duration,
                task=task,
                is_break=False,
            ))
            reserve(preferred, preferred + duration)
            placed = int(duration.total_seconds() / 60)
            if placed >= task.duration_minutes:
                task.completed = True
            else:
                # Remainder can pack into later gaps as a flexible task.
                task.duration_minutes -= placed
                task.start_time = None
                flexible_tasks.append(task)
                flexible_tasks.sort(
                    key=lambda t: (
                        0 if t.priority == TaskPriority.HIGH else (1 if t.priority == TaskPriority.MEDIUM else 2),
                        t.deadline if t.deadline else "9999-12-31",
                        t.duration_minutes,
                    ),
                )

        # --- Pass 2: place health breaks where they don't collide with reserved blocks ---
        for hb in health_breaks:
            if not hb.scheduled_time:
                continue
            b_start = hb.scheduled_time
            b_end = b_start + timedelta(minutes=hb.duration_minutes)
            if b_end > work_end:
                continue
            if overlaps(b_start, b_end):
                continue
            scheduled_items.append(ScheduledItem(
                start_time=b_start,
                end_time=b_end,
                break_item=hb,
                is_break=True,
            ))
            reserve(b_start, b_end)

        # --- Pass 3: pack flexible tasks into free gaps ---
        for task in flexible_tasks:
            remaining = task.duration_minutes
            cursor = start_date

            while remaining > 0:
                # Skip past occupied regions
                if task.splittable:
                    # Take the next free contiguous chunk (at least 15 min, or whatever remains)
                    # Find start of next free gap
                    t = cursor
                    if t < start_date:
                        t = start_date
                    # Advance past any occupation starting at/before t
                    changed = True
                    while changed:
                        changed = False
                        for occ_start, occ_end in occupied:
                            if occ_start <= t < occ_end:
                                t = occ_end
                                changed = True
                                break
                    if t >= work_end:
                        break

                    # Free until next occupation or work_end
                    gap_end = work_end
                    for occ_start, occ_end in occupied:
                        if occ_start > t:
                            gap_end = min(gap_end, occ_start)
                            break

                    available = int((gap_end - t).total_seconds() / 60)
                    if available < 15 and available < remaining:
                        cursor = gap_end
                        continue

                    chunk = min(remaining, available)
                    if chunk <= 0:
                        break
                    chunk_delta = timedelta(minutes=chunk)
                    scheduled_items.append(ScheduledItem(
                        start_time=t,
                        end_time=t + chunk_delta,
                        task=task,
                        is_break=False,
                    ))
                    reserve(t, t + chunk_delta)
                    remaining -= chunk
                    cursor = t + chunk_delta
                else:
                    # Unsplittable: need one contiguous free block
                    duration = timedelta(minutes=remaining)
                    slot = next_free_cursor(cursor, duration)
                    if slot is None:
                        break
                    scheduled_items.append(ScheduledItem(
                        start_time=slot,
                        end_time=slot + duration,
                        task=task,
                        is_break=False,
                    ))
                    reserve(slot, slot + duration)
                    remaining = 0

            if remaining <= 0:
                task.completed = True

        self.scheduled_items = sorted(scheduled_items, key=lambda x: x.start_time)
        return self.scheduled_items
    
    def print_schedule(self):
        """Print a formatted schedule."""
        if not self.scheduled_items:
            print("No schedule generated. Add tasks and call schedule_tasks() first.")
            return
        
        print("\n" + "="*80)
        print("📅 YOUR HEALTH-AWARE WORK SCHEDULE")
        print("="*80 + "\n")
        
        for item in self.scheduled_items:
            start_str = item.start_time.strftime("%H:%M")
            end_str = item.end_time.strftime("%H:%M")
            duration = (item.end_time - item.start_time).total_seconds() / 60
            
            if item.is_break:
                break_emoji = {
                    "physical": "🏃",
                    "mental": "🧘",
                    "hydration": "💧",
                    "meal": "🍽️"
                }.get(item.break_item.type, "☕")
                
                print(f"{start_str} - {end_str} ({int(duration)} min) {break_emoji} BREAK")
                print(f"   {item.break_item.description}")
            else:
                priority_emoji = {
                    "high": "🔴",
                    "medium": "🟡",
                    "low": "🟢"
                }.get(item.task.priority.value, "⚪")
                
                type_emoji = {
                    "focus": "🎯",
                    "meeting": "👥",
                    "admin": "📋",
                    "creative": "✨",
                    "learning": "📚"
                }.get(item.task.task_type.value, "📝")
                
                print(f"{start_str} - {end_str} ({int(duration)} min) {priority_emoji} {type_emoji} {item.task.name}")
                if item.task.description:
                    print(f"   {item.task.description}")
            
            print()
        
        print("="*80)
        print("💡 Health Tips:")
        print("   • Take all breaks seriously - they're essential for your wellbeing")
        print("   • During physical breaks, actually move - walk, stretch, do light exercises")
        print("   • Mental breaks are for rest - avoid screens if possible")
        print("   • Stay hydrated throughout the day")
        print("   • If you feel overwhelmed, adjust the schedule - your health comes first!")
        print("="*80 + "\n")
    
    def get_health_summary(self) -> Dict:
        """Get a summary of health breaks scheduled."""
        if not self.scheduled_items:
            return {}
        
        breaks = [item for item in self.scheduled_items if item.is_break]
        total_break_time = sum(
            (item.end_time - item.start_time).total_seconds() / 60
            for item in breaks
        )
        
        break_types = {}
        for item in breaks:
            if item.break_item:
                break_type = item.break_item.type
                break_types[break_type] = break_types.get(break_type, 0) + 1
        
        return {
            "total_breaks": len(breaks),
            "total_break_time_minutes": int(total_break_time),
            "break_types": break_types
        }
    
    def save_to_file(self, filename: str = "schedule.json"):
        """Save the schedule to a JSON file."""
        schedule_data = {
            "scheduled_items": [
                {
                    "start_time": item.start_time.isoformat(),
                    "end_time": item.end_time.isoformat(),
                    "is_break": item.is_break,
                    "task": {
                        "name": item.task.name,
                        "duration_minutes": item.task.duration_minutes,
                        "priority": item.task.priority.value,
                        "task_type": item.task.task_type.value,
                        "description": item.task.description
                    } if item.task else None,
                    "break_item": {
                        "type": item.break_item.type,
                        "duration_minutes": item.break_item.duration_minutes,
                        "description": item.break_item.description
                    } if item.break_item else None
                }
                for item in self.scheduled_items
            ]
        }
        
        with open(filename, 'w') as f:
            json.dump(schedule_data, f, indent=2)
        
        print(f"Schedule saved to {filename}")


def main():
    """Example usage of the Health-Aware Task Manager."""
    manager = HealthAwareTaskManager(
        work_start_hour=9,
        work_end_hour=17,
        focus_block_max_hours=2.0,
        break_interval_minutes=90,
        lunch_duration_minutes=60,
        lunch_hour=13
    )
    
    print("Welcome to your Health-Aware Task Manager! 👋")
    print("I'll help you organize your tasks while prioritizing your health.\n")
    
    # Example: Add some tasks
    print("Adding example tasks...")
    manager.add_task("Review project proposal", 60, "high", "focus", description="Deep work needed")
    manager.add_task("Team standup meeting", 30, "high", "meeting")
    manager.add_task("Update documentation", 45, "medium", "admin")
    manager.add_task("Learn new framework", 90, "low", "learning")
    manager.add_task("Design new feature", 120, "high", "creative")
    manager.add_task("Respond to emails", 30, "medium", "admin")
    
    # Schedule tasks
    print("Scheduling tasks with health breaks...\n")
    manager.schedule_tasks()
    
    # Print schedule
    manager.print_schedule()
    
    # Show health summary
    health_summary = manager.get_health_summary()
    print("\n📊 Health Summary:")
    print(f"   Total breaks: {health_summary.get('total_breaks', 0)}")
    print(f"   Total break time: {health_summary.get('total_break_time_minutes', 0)} minutes")
    print(f"   Break types: {health_summary.get('break_types', {})}")
    
    # Save schedule
    manager.save_to_file()


if __name__ == "__main__":
    # Fix Windows encoding for CLI
    if sys.platform == 'win32' and hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')
        sys.stderr.reconfigure(encoding='utf-8', errors='replace')
    main()
