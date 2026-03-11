"""
Health-Aware Task Manager
A task management system that schedules your work tasks while prioritizing your health.
"""

import sys
import os

from datetime import datetime, timedelta
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
        description: str = ""
    ):
        """Add a new task to the manager."""
        task = Task(
            name=name,
            duration_minutes=duration_minutes,
            priority=TaskPriority(priority.lower()),
            task_type=TaskType(task_type.lower()),
            deadline=deadline,
            description=description
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
        Prioritizes high-priority tasks and ensures health breaks are included.
        """
        if not self.tasks:
            return []
        
        if start_date is None:
            start_date = datetime.now().replace(hour=self.work_start_hour, minute=0, second=0, microsecond=0)
            if start_date < datetime.now():
                start_date = start_date + timedelta(days=1)
        
        # Sort tasks by priority and deadline
        sorted_tasks = sorted(
            self.tasks,
            key=lambda t: (
                t.priority.value == "high",
                t.deadline if t.deadline else "9999-12-31",
                t.duration_minutes
            ),
            reverse=True
        )
        
        scheduled_items: List[ScheduledItem] = []
        current_time = start_date
        work_end = start_date.replace(hour=self.work_end_hour, minute=0, second=0, microsecond=0)
        
        # Create all health breaks for the day
        health_breaks = self._create_health_breaks(start_date, work_end)
        break_index = 0
        
        # Track focus time for breaks
        focus_time_accumulated = timedelta(0)
        last_break_time = current_time
        
        for task in sorted_tasks:
            if task.completed:
                continue
            
            # Check if we need a break before this task
            time_since_break = current_time - last_break_time
            if time_since_break.total_seconds() >= self.break_interval_minutes * 60:
                # Insert a break
                break_duration = timedelta(minutes=10)
                if current_time + break_duration > work_end:
                    break
                
                scheduled_items.append(ScheduledItem(
                    start_time=current_time,
                    end_time=current_time + break_duration,
                    break_item=HealthBreak(
                        type="physical",
                        duration_minutes=10,
                        description="Physical break - Stand up, stretch, walk around"
                    ),
                    is_break=True
                ))
                current_time += break_duration
                last_break_time = current_time
                focus_time_accumulated = timedelta(0)
            
            # Check if we've exceeded max focus block
            if focus_time_accumulated.total_seconds() >= self.focus_block_max_hours * 3600:
                # Mandatory longer break
                long_break = timedelta(minutes=20)
                if current_time + long_break > work_end:
                    break
                
                scheduled_items.append(ScheduledItem(
                    start_time=current_time,
                    end_time=current_time + long_break,
                    break_item=HealthBreak(
                        type="mental",
                        duration_minutes=20,
                        description="Extended mental break - You've been focusing hard, take a proper rest"
                    ),
                    is_break=True
                ))
                current_time += long_break
                last_break_time = current_time
                focus_time_accumulated = timedelta(0)
            
            # Check if there's a scheduled health break coming up
            while break_index < len(health_breaks):
                next_break = health_breaks[break_index]
                if next_break.scheduled_time and next_break.scheduled_time <= current_time:
                    # Schedule this break
                    break_duration = timedelta(minutes=next_break.duration_minutes)
                    if current_time + break_duration > work_end:
                        break
                    
                    scheduled_items.append(ScheduledItem(
                        start_time=current_time,
                        end_time=current_time + break_duration,
                        break_item=next_break,
                        is_break=True
                    ))
                    current_time += break_duration
                    last_break_time = current_time
                    focus_time_accumulated = timedelta(0)
                    break_index += 1
                elif next_break.scheduled_time and next_break.scheduled_time < current_time + timedelta(minutes=task.duration_minutes):
                    # Break is coming during this task, schedule task up to break
                    task_duration_until_break = (next_break.scheduled_time - current_time).total_seconds() / 60
                    if task_duration_until_break >= 15:  # Only if meaningful time
                        scheduled_items.append(ScheduledItem(
                            start_time=current_time,
                            end_time=next_break.scheduled_time,
                            task=task,
                            is_break=False
                        ))
                        focus_time_accumulated += timedelta(minutes=task_duration_until_break)
                        current_time = next_break.scheduled_time
                        
                        # Schedule the break
                        break_duration = timedelta(minutes=next_break.duration_minutes)
                        scheduled_items.append(ScheduledItem(
                            start_time=current_time,
                            end_time=current_time + break_duration,
                            break_item=next_break,
                            is_break=True
                        ))
                        current_time += break_duration
                        last_break_time = current_time
                        focus_time_accumulated = timedelta(0)
                        break_index += 1
                        
                        # Continue task after break if needed
                        remaining_task_time = task.duration_minutes - task_duration_until_break
                        if remaining_task_time > 0:
                            task.duration_minutes = remaining_task_time
                        else:
                            task.completed = True
                            break
                    else:
                        break_index += 1
                else:
                    break
            
            # Check if we have time for this task
            task_duration = timedelta(minutes=task.duration_minutes)
            if current_time + task_duration > work_end:
                # Not enough time today, skip or reschedule
                break
            
            # Schedule the task
            scheduled_items.append(ScheduledItem(
                start_time=current_time,
                end_time=current_time + task_duration,
                task=task,
                is_break=False
            ))
            focus_time_accumulated += task_duration
            current_time += task_duration
            task.completed = True
        
        # Add any remaining health breaks
        while break_index < len(health_breaks):
            next_break = health_breaks[break_index]
            if next_break.scheduled_time and next_break.scheduled_time < work_end:
                if current_time < next_break.scheduled_time:
                    current_time = next_break.scheduled_time
                break_duration = timedelta(minutes=next_break.duration_minutes)
                if current_time + break_duration <= work_end:
                    scheduled_items.append(ScheduledItem(
                        start_time=current_time,
                        end_time=current_time + break_duration,
                        break_item=next_break,
                        is_break=True
                    ))
                    current_time += break_duration
            break_index += 1
        
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
