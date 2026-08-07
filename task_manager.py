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
        """Generate health breaks between start and end time."""
        breaks = []
        current_time = start_time
        
        # Lunch break
        lunch_time = current_time.replace(hour=self.lunch_hour, minute=0, second=0, microsecond=0)
        if start_time <= lunch_time < end_time:
            breaks.append(HealthBreak(
                type="meal",
                duration_minutes=self.lunch_duration_minutes,
                description="Lunch break - Step away from your desk, eat mindfully",
                scheduled_time=lunch_time
            ))
        
        # Regular breaks
        while current_time < end_time:
            # Skip if lunch is coming soon
            next_break_time = current_time + timedelta(minutes=self.break_interval_minutes)
            if next_break_time < end_time:
                # Determine break type based on time since last break
                break_type = "physical"
                break_desc = "Physical break - Stand up, stretch, walk around (5-10 min)"
                
                # Every 3rd break is a mental break
                if len(breaks) % 3 == 0 and breaks:
                    break_type = "mental"
                    break_desc = "Mental break - Deep breathing, meditation, or just rest (10-15 min)"
                
                breaks.append(HealthBreak(
                    type=break_type,
                    duration_minutes=15 if break_type == "mental" else 10,
                    description=break_desc,
                    scheduled_time=next_break_time
                ))
                current_time = next_break_time
            else:
                break
        
        # Hydration reminders (every 60 minutes, but not during breaks)
        hydration_time = start_time
        while hydration_time < end_time:
            hydration_time += timedelta(minutes=60)
            if hydration_time < end_time:
                # Check if it's not too close to a scheduled break
                too_close = False
                for br in breaks:
                    if br.scheduled_time and abs((hydration_time - br.scheduled_time).total_seconds()) < 300:
                        too_close = True
                        break
                if not too_close:
                    breaks.append(HealthBreak(
                        type="hydration",
                        duration_minutes=1,
                        description="💧 Hydration reminder - Drink water!",
                        scheduled_time=hydration_time
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
            duration = timedelta(minutes=task.duration_minutes)
            if preferred < start_date or preferred + duration > work_end:
                continue
            if overlaps(preferred, preferred + duration):
                # Try the next free slot at/after preferred (still contiguous)
                alt = next_free_cursor(preferred, duration)
                if alt is None:
                    continue
                preferred = alt
            scheduled_items.append(ScheduledItem(
                start_time=preferred,
                end_time=preferred + duration,
                task=task,
                is_break=False,
            ))
            reserve(preferred, preferred + duration)
            task.completed = True

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
