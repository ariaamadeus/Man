# Health-Aware Task Manager 👨‍💼💚

Your personal manager that organizes your work tasks while prioritizing your health and wellbeing.

## Overview

This task manager doesn't just schedule your work - it ensures you take care of your body and mind by:

- 🏃 **Automatic physical breaks** - Regular movement and stretching reminders
- 🧘 **Mental health breaks** - Scheduled rest periods to prevent burnout
- 💧 **Hydration reminders** - Regular water intake prompts
- 🍽️ **Meal scheduling** - Ensures you have proper lunch breaks
- ⚖️ **Work-life balance** - Prevents overloading and respects your limits
- 🎯 **Smart scheduling** - Prioritizes tasks while maintaining health

## Features

### Health-First Approach
- Breaks every 90 minutes (configurable)
- Extended mental breaks after 2 hours of focused work
- Automatic lunch break scheduling
- Hydration reminders every hour
- Prevents task overload

### Task Management
- Priority-based scheduling (High/Medium/Low)
- Multiple task types (Focus, Meeting, Admin, Creative, Learning)
- Deadline awareness
- Duration-based planning
- Visual schedule with emojis

## Installation

```bash
# Clone or download this repository
cd manager

# Create a virtual environment (recommended)
python -m venv venv
# Windows: venv\Scripts\activate
# macOS/Linux: source venv/bin/activate

# Install dependencies
pip install -r requirements.txt
```

## Usage

### Web app (Django)

Run the web application:

```bash
# First time: apply migrations
python manage.py migrate

# Start the development server
python manage.py runserver
```

Open **http://127.0.0.1:8000/** in your browser. You can:

- **Add / edit / delete tasks** and mark them done
- **Pick a date** and see your health-aware schedule (with breaks and lunch)
- **Change settings**: work hours, break interval, lunch time

Optional: create a superuser to use the admin at `/admin/`:

```bash
python manage.py createsuperuser
```

### Interactive CLI

Run the interactive CLI:

```bash
python cli.py
```

This will give you a menu-driven interface where you can:
1. Add tasks
2. View all tasks
3. Generate a health-aware schedule
4. View your schedule
5. Configure settings
6. See health summary
7. Save schedule to file

### Programmatic Usage

You can also use it as a Python module:

```python
from task_manager import HealthAwareTaskManager

# Create manager
manager = HealthAwareTaskManager(
    work_start_hour=9,
    work_end_hour=17,
    focus_block_max_hours=2.0,
    break_interval_minutes=90,
    lunch_duration_minutes=60,
    lunch_hour=13
)

# Add tasks
manager.add_task("Review proposal", 60, "high", "focus")
manager.add_task("Team meeting", 30, "high", "meeting")
manager.add_task("Update docs", 45, "medium", "admin")

# Generate schedule
manager.schedule_tasks()

# View schedule
manager.print_schedule()

# Get health summary
summary = manager.get_health_summary()
print(summary)

# Save to file
manager.save_to_file("my_schedule.json")
```

## Configuration

You can customize:

- **Work hours**: When your workday starts and ends
- **Focus block max**: Maximum hours of continuous focus before mandatory break
- **Break interval**: How often to take breaks (in minutes)
- **Lunch**: When and how long your lunch break is

## Example Schedule Output

```
================================================================================
📅 YOUR HEALTH-AWARE WORK SCHEDULE
================================================================================

09:00 - 10:00 (60 min) 🔴 🎯 Review project proposal
   Deep work needed

10:00 - 10:10 (10 min) 🏃 BREAK
   Physical break - Stand up, stretch, walk around (5-10 min)

10:10 - 10:40 (30 min) 🔴 👥 Team standup meeting

10:40 - 10:41 (1 min) 💧 BREAK
   💧 Hydration reminder - Drink water!

10:41 - 11:26 (45 min) 🟡 📋 Update documentation

11:26 - 11:36 (10 min) 🏃 BREAK
   Physical break - Stand up, stretch, walk around (5-10 min)

...

13:00 - 14:00 (60 min) 🍽️ BREAK
   Lunch break - Step away from your desk, eat mindfully

...
```

## Health Tips

The manager includes built-in health tips:

- Take all breaks seriously - they're essential for your wellbeing
- During physical breaks, actually move - walk, stretch, do light exercises
- Mental breaks are for rest - avoid screens if possible
- Stay hydrated throughout the day
- If you feel overwhelmed, adjust the schedule - your health comes first!

## Philosophy

**Your health is not negotiable.** 

This manager treats your physical and mental wellbeing as non-negotiable priorities. Work is important, but sustainable productivity requires taking care of yourself first.

## License

Free to use for your personal productivity and health!

---

**Remember**: You're not a machine. Take breaks, move your body, rest your mind, and stay hydrated. Your future self will thank you! 💚
