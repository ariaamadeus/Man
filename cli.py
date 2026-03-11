"""
Interactive CLI for Health-Aware Task Manager
"""

import sys
import os

# Fix Windows encoding issues
if sys.platform == 'win32':
    # Set UTF-8 encoding for console output
    if hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')
        sys.stderr.reconfigure(encoding='utf-8', errors='replace')
    else:
        # Fallback: set environment variable
        os.environ['PYTHONIOENCODING'] = 'utf-8'

from datetime import datetime
from task_manager import HealthAwareTaskManager, TaskPriority, TaskType


def print_welcome():
    print("\n" + "="*80)
    print("👋 Welcome to your Health-Aware Task Manager!")
    print("="*80)
    print("I'm here to help you organize your work while keeping you healthy.")
    print("I'll automatically schedule breaks, movement, and rest periods.")
    print("="*80 + "\n")


def get_user_input(prompt: str, default: str = None) -> str:
    """Get user input with optional default."""
    if default:
        response = input(f"{prompt} [{default}]: ").strip()
        return response if response else default
    return input(f"{prompt}: ").strip()


def add_task_interactive(manager: HealthAwareTaskManager):
    """Interactive task addition."""
    print("\n📝 Adding a new task...")
    
    name = get_user_input("Task name")
    if not name:
        print("❌ Task name is required!")
        return
    
    try:
        duration = int(get_user_input("Duration (minutes)", "60"))
    except ValueError:
        print("❌ Invalid duration!")
        return
    
    print("\nPriority levels:")
    print("  1. High (urgent/important)")
    print("  2. Medium (normal)")
    print("  3. Low (can wait)")
    priority_choice = get_user_input("Priority (1-3)", "2")
    priority_map = {"1": "high", "2": "medium", "3": "low"}
    priority = priority_map.get(priority_choice, "medium")
    
    print("\nTask types:")
    print("  1. Focus (deep work)")
    print("  2. Meeting")
    print("  3. Admin (emails, paperwork)")
    print("  4. Creative (design, writing)")
    print("  5. Learning")
    type_choice = get_user_input("Task type (1-5)", "1")
    type_map = {"1": "focus", "2": "meeting", "3": "admin", "4": "creative", "5": "learning"}
    task_type = type_map.get(type_choice, "focus")
    
    deadline = get_user_input("Deadline (YYYY-MM-DD, optional)", "")
    description = get_user_input("Description (optional)", "")
    
    manager.add_task(name, duration, priority, task_type, deadline if deadline else None, description)
    print(f"✅ Task '{name}' added successfully!")


def configure_manager(manager: HealthAwareTaskManager):
    """Configure manager settings."""
    print("\n⚙️  Configuration")
    print("Current settings:")
    print(f"  Work hours: {manager.work_start_hour}:00 - {manager.work_end_hour}:00")
    print(f"  Max focus block: {manager.focus_block_max_hours} hours")
    print(f"  Break interval: {manager.break_interval_minutes} minutes")
    print(f"  Lunch: {manager.lunch_hour}:00 ({manager.lunch_duration_minutes} min)")
    
    print("\nWould you like to change these? (y/n)")
    if input().strip().lower() != 'y':
        return
    
    try:
        start_hour = int(get_user_input(f"Work start hour", str(manager.work_start_hour)))
        end_hour = int(get_user_input(f"Work end hour", str(manager.work_end_hour)))
        max_focus = float(get_user_input(f"Max focus block (hours)", str(manager.focus_block_max_hours)))
        break_interval = int(get_user_input(f"Break interval (minutes)", str(manager.break_interval_minutes)))
        lunch_hour = int(get_user_input(f"Lunch hour", str(manager.lunch_hour)))
        lunch_duration = int(get_user_input(f"Lunch duration (minutes)", str(manager.lunch_duration_minutes)))
        
        manager.work_start_hour = start_hour
        manager.work_end_hour = end_hour
        manager.focus_block_max_hours = max_focus
        manager.break_interval_minutes = break_interval
        manager.lunch_hour = lunch_hour
        manager.lunch_duration_minutes = lunch_duration
        
        print("✅ Configuration updated!")
    except ValueError:
        print("❌ Invalid input!")


def main_menu(manager: HealthAwareTaskManager):
    """Main interactive menu."""
    while True:
        print("\n" + "-"*80)
        print("📋 MAIN MENU")
        print("-"*80)
        print("1. Add a task")
        print("2. View all tasks")
        print("3. Generate schedule")
        print("4. View schedule")
        print("5. Configure settings")
        print("6. Health summary")
        print("7. Save schedule to file")
        print("8. Exit")
        print("-"*80)
        
        choice = input("\nWhat would you like to do? ").strip()
        
        if choice == "1":
            add_task_interactive(manager)
        
        elif choice == "2":
            if not manager.tasks:
                print("\n📭 No tasks added yet.")
            else:
                print("\n📋 Your Tasks:")
                for i, task in enumerate(manager.tasks, 1):
                    status = "✅" if task.completed else "⏳"
                    print(f"\n{status} {i}. {task.name}")
                    print(f"   Duration: {task.duration_minutes} min")
                    print(f"   Priority: {task.priority.value.upper()}")
                    print(f"   Type: {task.task_type.value}")
                    if task.deadline:
                        print(f"   Deadline: {task.deadline}")
                    if task.description:
                        print(f"   Description: {task.description}")
        
        elif choice == "3":
            if not manager.tasks:
                print("\n❌ Please add tasks first!")
                continue
            
            print("\n📅 Generating your health-aware schedule...")
            start_date_str = get_user_input("Start date (YYYY-MM-DD, or press Enter for today/tomorrow)", "")
            
            if start_date_str:
                try:
                    start_date = datetime.strptime(start_date_str, "%Y-%m-%d")
                    start_date = start_date.replace(hour=manager.work_start_hour, minute=0, second=0, microsecond=0)
                except ValueError:
                    print("❌ Invalid date format! Using default.")
                    start_date = None
            else:
                start_date = None
            
            manager.schedule_tasks(start_date)
            print("✅ Schedule generated! View it with option 4.")
        
        elif choice == "4":
            if not manager.scheduled_items:
                print("\n❌ No schedule generated yet. Generate one with option 3.")
            else:
                manager.print_schedule()
        
        elif choice == "5":
            configure_manager(manager)
        
        elif choice == "6":
            if not manager.scheduled_items:
                print("\n❌ No schedule generated yet. Generate one with option 3.")
            else:
                health_summary = manager.get_health_summary()
                print("\n📊 Health Summary:")
                print(f"   Total breaks scheduled: {health_summary.get('total_breaks', 0)}")
                print(f"   Total break time: {health_summary.get('total_break_time_minutes', 0)} minutes")
                print(f"   Break breakdown:")
                for break_type, count in health_summary.get('break_types', {}).items():
                    emoji = {"physical": "🏃", "mental": "🧘", "hydration": "💧", "meal": "🍽️"}.get(break_type, "☕")
                    print(f"     {emoji} {break_type.capitalize()}: {count}")
        
        elif choice == "7":
            if not manager.scheduled_items:
                print("\n❌ No schedule generated yet. Generate one with option 3.")
            else:
                filename = get_user_input("Filename", "schedule.json")
                manager.save_to_file(filename)
        
        elif choice == "8":
            print("\n👋 Take care of yourself! Remember: your health comes first!")
            break
        
        else:
            print("\n❌ Invalid choice. Please try again.")


def main():
    """Main entry point."""
    print_welcome()
    
    # Initialize manager with default settings
    manager = HealthAwareTaskManager()
    
    # Check for command line arguments (quick task addition)
    if len(sys.argv) > 1:
        if sys.argv[1] == "--help" or sys.argv[1] == "-h":
            print("\nUsage:")
            print("  python cli.py              - Interactive mode")
            print("  python cli.py --help      - Show this help")
            return
    
    # Start interactive menu
    try:
        main_menu(manager)
    except KeyboardInterrupt:
        print("\n\n👋 Take care! Your health comes first!")
    except Exception as e:
        print(f"\n❌ An error occurred: {e}")


if __name__ == "__main__":
    main()
