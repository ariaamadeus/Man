from datetime import date
from django.shortcuts import render, redirect, get_object_or_404
from django.views.decorators.http import require_http_methods, require_POST
from django.contrib import messages
from .models import Task, ScheduleSettings
from .forms import TaskForm, ScheduleSettingsForm
from .services import build_schedule


def home(request):
    tasks = Task.objects.all()
    settings = ScheduleSettings.get_settings()
    schedule_date = request.GET.get('date')
    if schedule_date:
        try:
            schedule_date = date.fromisoformat(schedule_date)
        except ValueError:
            schedule_date = date.today()
    else:
        schedule_date = date.today()

    schedule_items = []
    health_summary = {}
    if tasks.filter(completed=False).exists():
        schedule_items, health_summary = build_schedule(
            tasks, settings, schedule_date=schedule_date
        )

    return render(request, 'tasks/home.html', {
        'tasks': tasks,
        'schedule_items': schedule_items,
        'health_summary': health_summary,
        'schedule_date': schedule_date,
        'settings': settings,
    })


def task_add(request):
    if request.method == 'POST':
        form = TaskForm(request.POST)
        if form.is_valid():
            form.save()
            messages.success(request, 'Task added.')
            return redirect('tasks:home')
    else:
        form = TaskForm()
    return render(request, 'tasks/task_form.html', {'form': form, 'title': 'Add task'})


def task_edit(request, pk):
    task = get_object_or_404(Task, pk=pk)
    if request.method == 'POST':
        form = TaskForm(request.POST, instance=task)
        if form.is_valid():
            form.save()
            messages.success(request, 'Task updated.')
            return redirect('tasks:home')
    else:
        form = TaskForm(instance=task)
    return render(request, 'tasks/task_form.html', {'form': form, 'title': 'Edit task', 'task': task})


@require_POST
def task_delete(request, pk):
    task = get_object_or_404(Task, pk=pk)
    task.delete()
    messages.success(request, 'Task deleted.')
    return redirect('tasks:home')


@require_POST
def task_toggle_done(request, pk):
    task = get_object_or_404(Task, pk=pk)
    task.completed = not task.completed
    task.save()
    messages.success(request, 'Task marked as done.' if task.completed else 'Task marked as not done.')
    return redirect('tasks:home')


def settings_view(request):
    settings = ScheduleSettings.get_settings()
    if request.method == 'POST':
        form = ScheduleSettingsForm(request.POST, instance=settings)
        if form.is_valid():
            form.save()
            messages.success(request, 'Settings saved.')
            return redirect('tasks:home')
    else:
        form = ScheduleSettingsForm(instance=settings)
    return render(request, 'tasks/settings.html', {'form': form})
