from datetime import date, datetime, time, timedelta
import json
import secrets

from django.shortcuts import render, redirect, get_object_or_404
from django.views.decorators.http import require_POST
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.urls import reverse
from django.http import HttpResponseRedirect, JsonResponse
from .models import Task, TaskTimeLog, ScheduleSettings, GoogleCalendarConnection
from .forms import TaskForm, ScheduleSettingsForm
from .services import build_schedule
from .whatsapp import get_mqtt_status
from . import google_calendar as gcal

# Vertical scale for the day timeline (px per minute of the workday).
TIMELINE_PX_PER_MINUTE = 1.4


def _sync_calendar(user):
    gcal.sync_user_schedule_safe(user)


@login_required
def home(request):
    tasks = list(Task.objects.filter(user=request.user))
    schedule_settings = ScheduleSettings.get_for_user(request.user)

    # Keep server-rendered "now" in sync with the UI "Realtime" clock (UTC+7).
    # This also drives the "● Now" highlighting in the schedule list.
    now = datetime.utcnow() + timedelta(hours=7)
    today = now.date()

    schedule_date = request.GET.get('date')
    if schedule_date:
        try:
            schedule_date = date.fromisoformat(schedule_date)
        except ValueError:
            schedule_date = today
    else:
        schedule_date = today

    task_qs = Task.objects.filter(user=request.user)
    schedule_items = []
    health_summary = {}
    if task_qs.filter(completed=False).exists():
        schedule_items, health_summary = build_schedule(
            task_qs, schedule_settings, schedule_date=schedule_date
        )

    # Attach per-task progress/waste for the viewed day (for schedule + list UI).
    task_progress = {}
    for t in tasks:
        progress = {
            'done_today': t.done_minutes_for_date(schedule_date),
            'wasted_today': t.wasted_minutes_for_date(schedule_date),
            'remaining': t.remaining_minutes(on_date=schedule_date),
            'wasted_total': t.wasted_minutes,
            'done_total': t.done_minutes,
        }
        task_progress[t.pk] = progress
        t.display_remaining = progress['remaining']
        t.display_wasted_today = progress['wasted_today']

    work_start_min = schedule_settings.work_start_hour * 60
    work_end_min = schedule_settings.work_end_hour * 60
    workday_minutes = max(1, work_end_min - work_start_min)
    timeline_height = int(workday_minutes * TIMELINE_PX_PER_MINUTE)
    hour_marks = [
        {
            'hour': hour,
            'label': f'{hour:02d}:00',
            'top_px': round((hour * 60 - work_start_min) * TIMELINE_PX_PER_MINUTE, 1),
        }
        for hour in range(schedule_settings.work_start_hour, schedule_settings.work_end_hour + 1)
    ]

    for item in schedule_items:
        tid = item.get('task_id')
        if tid and tid in task_progress:
            item['done_today'] = task_progress[tid]['done_today']
            item['wasted_today'] = task_progress[tid]['wasted_today']
            item['remaining_total'] = task_progress[tid]['remaining']

        start_dt = item['start_time']
        start_min = start_dt.hour * 60 + start_dt.minute
        offset = max(0, start_min - work_start_min)
        item['top_px'] = round(offset * TIMELINE_PX_PER_MINUTE, 1)
        item['height_px'] = max(28, round(item['duration_minutes'] * TIMELINE_PX_PER_MINUTE, 1))
        item['start_hm'] = start_dt.strftime('%H:%M')

    day_logs = (
        TaskTimeLog.objects.filter(user=request.user, schedule_date=schedule_date)
        .select_related('task')
        .order_by('-created_at')[:20]
    )

    return render(request, 'tasks/home.html', {
        'tasks': tasks,
        'schedule_items': schedule_items,
        'health_summary': health_summary,
        'schedule_date': schedule_date,
        'settings': schedule_settings,
        'now': now,
        'today': today,
        'task_progress': task_progress,
        'day_logs': day_logs,
        'timeline_height': timeline_height,
        'timeline_px_per_minute': TIMELINE_PX_PER_MINUTE,
        'work_start_min': work_start_min,
        'work_end_min': work_end_min,
        'hour_marks': hour_marks,
    })


@login_required
def task_add(request):
    if request.method == 'POST':
        form = TaskForm(request.POST)
        if form.is_valid():
            task = form.save(commit=False)
            task.user = request.user
            task.save()
            _sync_calendar(request.user)
            messages.success(request, 'Task added.')
            return redirect('tasks:home')
    else:
        form = TaskForm()
    return render(request, 'tasks/task_form.html', {'form': form, 'title': 'Add task'})


@login_required
def task_edit(request, pk):
    task = get_object_or_404(Task, pk=pk, user=request.user)
    if request.method == 'POST':
        form = TaskForm(request.POST, instance=task)
        if form.is_valid():
            form.save()
            _sync_calendar(request.user)
            messages.success(request, 'Task updated.')
            return redirect('tasks:home')
    else:
        form = TaskForm(instance=task)
    return render(request, 'tasks/task_form.html', {'form': form, 'title': 'Edit task', 'task': task})


@login_required
@require_POST
def task_delete(request, pk):
    task = get_object_or_404(Task, pk=pk, user=request.user)
    task.delete()
    _sync_calendar(request.user)
    messages.success(request, 'Task deleted.')
    return redirect('tasks:home')


@login_required
@require_POST
def task_toggle_done(request, pk):
    task = get_object_or_404(Task, pk=pk, user=request.user)
    task.completed = not task.completed
    task.save()
    _sync_calendar(request.user)
    messages.success(request, 'Task marked as done.' if task.completed else 'Task marked as not done.')
    return redirect('tasks:home')


@login_required
@require_POST
def task_reschedule(request, pk):
    """Pin a task to a new clock time (used by drag-and-drop on the day timeline)."""
    task = get_object_or_404(Task, pk=pk, user=request.user)
    start_hm = (request.POST.get('start_time') or '').strip()
    schedule_date_raw = (request.POST.get('schedule_date') or '').strip()
    wants_json = (
        'application/json' in (request.headers.get('Accept') or '')
        or request.headers.get('X-Requested-With') == 'XMLHttpRequest'
    )

    try:
        schedule_date = date.fromisoformat(schedule_date_raw) if schedule_date_raw else date.today()
    except ValueError:
        schedule_date = date.today()

    try:
        hour_s, minute_s = start_hm.split(':', 1)
        hour, minute = int(hour_s), int(minute_s)
        if not (0 <= hour <= 23 and 0 <= minute <= 59):
            raise ValueError('out of range')
        # Snap to 5-minute grid.
        minute = (minute // 5) * 5
        new_time = time(hour=hour, minute=minute)
    except (TypeError, ValueError):
        msg = 'Invalid start time.'
        if wants_json:
            return JsonResponse({'ok': False, 'error': msg}, status=400)
        messages.error(request, msg)
        return HttpResponseRedirect(f"{reverse('tasks:home')}?date={schedule_date.isoformat()}")

    settings = ScheduleSettings.get_for_user(request.user)
    start_min = hour * 60 + minute
    end_min = start_min + task.remaining_minutes(on_date=schedule_date)
    work_start = settings.work_start_hour * 60
    work_end = settings.work_end_hour * 60
    if start_min < work_start or end_min > work_end:
        msg = (
            f'Time must fit within work hours '
            f'({settings.work_start_hour:02d}:00–{settings.work_end_hour:02d}:00).'
        )
        if wants_json:
            return JsonResponse({'ok': False, 'error': msg}, status=400)
        messages.error(request, msg)
        return HttpResponseRedirect(f"{reverse('tasks:home')}?date={schedule_date.isoformat()}")

    task.start_time = new_time
    task.save(update_fields=['start_time'])
    _sync_calendar(request.user)

    msg = f'Rescheduled “{task.name}” to {new_time.strftime("%H:%M")}.'
    if wants_json:
        return JsonResponse({
            'ok': True,
            'message': msg,
            'start_time': new_time.strftime('%H:%M'),
            'redirect': f"{reverse('tasks:home')}?date={schedule_date.isoformat()}",
        })
    messages.success(request, msg)
    return HttpResponseRedirect(f"{reverse('tasks:home')}?date={schedule_date.isoformat()}")


@login_required
@require_POST
def task_log_progress(request, pk):
    """Log how long was done/wasted on a slot; remaining duration is rescheduled."""
    task = get_object_or_404(Task, pk=pk, user=request.user)

    try:
        done_minutes = max(0, int(request.POST.get('done_minutes') or 0))
    except (TypeError, ValueError):
        done_minutes = 0
    try:
        wasted_minutes = max(0, int(request.POST.get('wasted_minutes') or 0))
    except (TypeError, ValueError):
        wasted_minutes = 0
    try:
        planned_minutes = max(0, int(request.POST.get('planned_minutes') or 0))
    except (TypeError, ValueError):
        planned_minutes = 0

    if done_minutes == 0 and wasted_minutes == 0:
        messages.warning(request, 'Enter done and/or wasted minutes.')
        return redirect('tasks:home')

    schedule_date_raw = request.POST.get('schedule_date') or ''
    try:
        schedule_date = date.fromisoformat(schedule_date_raw) if schedule_date_raw else date.today()
    except ValueError:
        schedule_date = date.today()

    slot_start = None
    slot_start_raw = (request.POST.get('slot_start') or '').strip()
    if slot_start_raw:
        try:
            slot_start = datetime.fromisoformat(slot_start_raw)
        except ValueError:
            slot_start = None

    remaining_before = task.remaining_minutes(on_date=schedule_date)
    if done_minutes > remaining_before:
        done_minutes = remaining_before

    TaskTimeLog.objects.create(
        task=task,
        user=request.user,
        schedule_date=schedule_date,
        slot_start=slot_start,
        planned_minutes=planned_minutes,
        done_minutes=done_minutes,
        wasted_minutes=wasted_minutes,
    )

    task.done_minutes = task.done_minutes + done_minutes
    task.wasted_minutes = task.wasted_minutes + wasted_minutes

    remaining_after = task.remaining_minutes(on_date=schedule_date)
    if remaining_after <= 0 and task.schedule_type == 'one_time':
        task.completed = True
        # Fully done — keep any pinned time as historical; no need to reschedule.
    elif remaining_after > 0 and done_minutes > 0:
        # Partial progress: clear pinned clock time so the leftover is free to
        # pack into a later gap instead of sticking to the original slot.
        task.start_time = None

    task.save()
    _sync_calendar(request.user)

    if task.completed:
        messages.success(
            request,
            f'Logged {done_minutes}m done'
            + (f', {wasted_minutes}m wasted' if wasted_minutes else '')
            + '. Task finished.',
        )
    else:
        messages.success(
            request,
            f'Logged {done_minutes}m done'
            + (f', {wasted_minutes}m wasted' if wasted_minutes else '')
            + f'. {remaining_after}m remaining rescheduled.',
        )

    return HttpResponseRedirect(f"{reverse('tasks:home')}?date={schedule_date.isoformat()}")


@login_required
def settings_view(request):
    schedule_settings = ScheduleSettings.get_for_user(request.user)
    if request.method == 'POST':
        form = ScheduleSettingsForm(request.POST, instance=schedule_settings)
        if form.is_valid():
            form.save()
            connection = GoogleCalendarConnection.objects.filter(user=request.user).first()
            if connection and connection.is_connected:
                sync_breaks = request.POST.get('sync_breaks') == 'on'
                if connection.sync_breaks != sync_breaks:
                    connection.sync_breaks = sync_breaks
                    connection.save(update_fields=['sync_breaks', 'updated_at'])
            _sync_calendar(request.user)
            messages.success(request, 'Settings saved.')
            return redirect('tasks:home')
    else:
        form = ScheduleSettingsForm(instance=schedule_settings)
    return render(request, 'tasks/settings.html', {
        'form': form,
        'mqtt_status': get_mqtt_status(request.user),
        'gcal_status': gcal.get_connection_status(request.user),
    })


@login_required
def google_connect(request):
    if not gcal.google_oauth_configured():
        messages.error(
            request,
            'Google Calendar is not configured. Upload credentials.json or set GOOGLE_CLIENT_ID / GOOGLE_CLIENT_SECRET.',
        )
        return redirect('tasks:settings')
    state = secrets.token_urlsafe(24)
    request.session['google_oauth_state'] = state
    auth_url, redirect_uri, code_verifier = gcal.get_authorization_url(state, request=request)
    request.session['google_oauth_redirect_uri'] = redirect_uri
    if code_verifier:
        request.session['google_oauth_code_verifier'] = code_verifier
    else:
        request.session.pop('google_oauth_code_verifier', None)
    return redirect(auth_url)


@login_required
def google_callback(request):
    if not gcal.google_oauth_configured():
        messages.error(request, 'Google Calendar is not configured.')
        return redirect('tasks:settings')

    error = request.GET.get('error')
    if error:
        messages.error(request, f'Google authorization failed: {error}')
        return redirect('tasks:settings')

    state = request.GET.get('state', '')
    expected = request.session.pop('google_oauth_state', None)
    redirect_uri = request.session.pop('google_oauth_redirect_uri', None) or gcal.get_redirect_uri(request)
    code_verifier = request.session.pop('google_oauth_code_verifier', None)
    if not expected or state != expected:
        messages.error(request, 'Invalid OAuth state. Please try connecting again.')
        return redirect('tasks:settings')

    code = request.GET.get('code')
    if not code:
        messages.error(request, 'Missing authorization code from Google.')
        return redirect('tasks:settings')

    try:
        token_data = gcal.exchange_code_for_tokens(
            code,
            redirect_uri=redirect_uri,
            code_verifier=code_verifier,
        )
        if not token_data.get('refresh_token'):
            # Re-consent may be needed; keep going if we already stored a refresh token.
            existing = GoogleCalendarConnection.objects.filter(user=request.user).first()
            if existing and existing.token_json:
                old = json.loads(existing.token_json)
                if old.get('refresh_token'):
                    token_data['refresh_token'] = old['refresh_token']
        if not token_data.get('refresh_token'):
            messages.error(
                request,
                'Google did not return a refresh token. Revoke access for this app in your Google Account and try again.',
            )
            return redirect('tasks:settings')

        connection, _ = GoogleCalendarConnection.objects.get_or_create(user=request.user)
        connection.token_json = json.dumps(token_data)
        connection.sync_enabled = True
        connection.last_sync_error = ''
        connection.save()
        result = gcal.sync_user_schedule(request.user)
        if result.get('ok'):
            messages.success(request, 'Google Calendar connected and schedule synced.')
        else:
            messages.warning(
                request,
                f"Connected, but initial sync failed: {result.get('error') or result.get('reason')}",
            )
    except Exception as exc:  # noqa: BLE001
        messages.error(request, f'Failed to connect Google Calendar: {exc}')
    return redirect('tasks:settings')


@login_required
@require_POST
def google_disconnect(request):
    gcal.clear_user_calendar_events(request.user)
    GoogleCalendarConnection.objects.filter(user=request.user).delete()
    messages.success(request, 'Google Calendar disconnected. Synced events were removed.')
    return redirect('tasks:settings')


@login_required
@require_POST
def google_sync_now(request):
    result = gcal.sync_user_schedule(request.user)
    if result.get('ok'):
        messages.success(
            request,
            f"Calendar synced — created {result.get('created', 0)}, "
            f"updated {result.get('updated', 0)}, deleted {result.get('deleted', 0)}, "
            f"unchanged {result.get('skipped', 0)}.",
        )
    elif result.get('skipped'):
        messages.warning(request, f"Sync skipped ({result.get('reason')}). Connect Google Calendar first.")
    else:
        messages.error(request, f"Sync failed: {result.get('error', 'unknown error')}")
    return redirect('tasks:settings')
