from django.conf import settings
from django.db import models
from django.db.models import Sum


class Task(models.Model):
    PRIORITY_CHOICES = [
        ('high', 'High'),
        ('medium', 'Medium'),
        ('low', 'Low'),
    ]
    TASK_TYPE_CHOICES = [
        ('focus', 'Focus'),
        ('meeting', 'Meeting'),
        ('admin', 'Admin'),
        ('creative', 'Creative'),
        ('learning', 'Learning'),
    ]
    SCHEDULE_TYPE_CHOICES = [
        ('one_time', 'One time'),
        ('recurring', 'Recurring'),
    ]
    RECURRENCE_UNIT_CHOICES = [
        ('daily', 'Daily'),
        ('weekly', 'Weekly'),
        ('monthly', 'Monthly'),
        ('yearly', 'Yearly'),
    ]
    DURATION_MODE_CHOICES = [
        ('per_task', 'Duration per task'),
        ('total_budget', 'Total duration (AI adjusts)'),
    ]

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='tasks',
    )
    name = models.CharField(max_length=200)
    duration_minutes = models.PositiveIntegerField(
        help_text="Current scheduled length for this task (session allocation).",
    )
    duration_mode = models.CharField(
        max_length=20,
        choices=DURATION_MODE_CHOICES,
        default='per_task',
        help_text="per_task = fixed length; total_budget = whole envelope for AI to allocate.",
    )
    total_duration_minutes = models.PositiveIntegerField(
        null=True,
        blank=True,
        help_text="Whole time budget when duration_mode is total_budget. AI may split/adjust session lengths.",
    )
    priority = models.CharField(max_length=10, choices=PRIORITY_CHOICES, default='medium')
    task_type = models.CharField(max_length=20, choices=TASK_TYPE_CHOICES, default='focus')
    schedule_type = models.CharField(max_length=20, choices=SCHEDULE_TYPE_CHOICES, default='one_time')
    recurrence_unit = models.CharField(max_length=20, choices=RECURRENCE_UNIT_CHOICES, null=True, blank=True)
    recurrence_every = models.PositiveIntegerField(null=True, blank=True)
    deadline = models.DateField(null=True, blank=True)
    starts_on = models.DateField(
        null=True,
        blank=True,
        help_text="If set, this task is only included in the schedule on or after this date.",
    )
    start_time = models.TimeField(
        null=True,
        blank=True,
        help_text="If set, the scheduler will try to place this task at this clock time.",
    )
    splittable = models.BooleanField(
        default=True,
        help_text="If false, health breaks will not split this task into multiple blocks.",
    )
    description = models.TextField(blank=True)
    completed = models.BooleanField(default=False)
    done_minutes = models.PositiveIntegerField(
        default=0,
        help_text="Productive minutes already completed (one-time tasks; recurring uses per-day logs).",
    )
    wasted_minutes = models.PositiveIntegerField(
        default=0,
        help_text="Cumulative wasted minutes across logged sessions.",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']

    def save(self, *args, **kwargs):
        # Meetings must stay contiguous (cannot be split around breaks).
        if self.task_type == 'meeting':
            self.splittable = False
        super().save(*args, **kwargs)

    @property
    def planned_budget_minutes(self):
        """Overall planned minutes: total budget if set, otherwise fixed task duration."""
        if self.duration_mode == 'total_budget' and self.total_duration_minutes:
            return self.total_duration_minutes
        return self.duration_minutes

    @staticmethod
    def split_minutes(total_minutes):
        """Break minutes into (months, days, hours, minutes). 1 month = 30 days."""
        total = max(0, int(total_minutes or 0))
        months = total // (30 * 24 * 60)
        rem = total % (30 * 24 * 60)
        days = rem // (24 * 60)
        rem %= 24 * 60
        hours = rem // 60
        minutes = rem % 60
        return months, days, hours, minutes

    @staticmethod
    def combine_duration_parts(months=0, days=0, hours=0, minutes=0):
        """Convert month/day/hour/minute parts to total minutes. 1 month = 30 days."""
        return (
            int(months or 0) * 30 * 24 * 60
            + int(days or 0) * 24 * 60
            + int(hours or 0) * 60
            + int(minutes or 0)
        )

    def format_duration_parts(self, total_minutes=None):
        """Human-readable duration, e.g. '1mo 2d 3h 15m'."""
        minutes = self.planned_budget_minutes if total_minutes is None else total_minutes
        months, days, hours, mins = self.split_minutes(minutes)
        parts = []
        if months:
            parts.append(f'{months}mo')
        if days:
            parts.append(f'{days}d')
        if hours:
            parts.append(f'{hours}h')
        if mins or not parts:
            parts.append(f'{mins}m')
        return ' '.join(parts)

    def done_minutes_for_date(self, on_date):
        """Minutes already done that should reduce scheduling for this date."""
        if self.schedule_type == 'recurring':
            total = self.time_logs.filter(schedule_date=on_date).aggregate(
                s=Sum('done_minutes')
            )['s']
            return total or 0
        return self.done_minutes

    def remaining_minutes(self, on_date=None):
        done = self.done_minutes_for_date(on_date) if on_date is not None else self.done_minutes
        # Until AI allocates session chunks, schedule against the overall budget.
        return max(0, self.planned_budget_minutes - done)

    def wasted_minutes_for_date(self, on_date):
        total = self.time_logs.filter(schedule_date=on_date).aggregate(
            s=Sum('wasted_minutes')
        )['s']
        return total or 0

    def __str__(self):
        return self.name


class TaskTimeLog(models.Model):
    """One progress/waste entry for a scheduled task slot (an 'event')."""
    task = models.ForeignKey(Task, on_delete=models.CASCADE, related_name='time_logs')
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='task_time_logs',
    )
    schedule_date = models.DateField()
    slot_start = models.DateTimeField(
        null=True,
        blank=True,
        help_text="Start of the schedule slot this log applies to, if known.",
    )
    planned_minutes = models.PositiveIntegerField(
        default=0,
        help_text="Planned duration of the slot when progress was logged.",
    )
    done_minutes = models.PositiveIntegerField(default=0)
    wasted_minutes = models.PositiveIntegerField(default=0)
    note = models.CharField(max_length=255, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['user', 'schedule_date']),
            models.Index(fields=['task', 'schedule_date']),
        ]

    def __str__(self):
        return (
            f"{self.task.name} @ {self.schedule_date}: "
            f"+{self.done_minutes}m done, +{self.wasted_minutes}m wasted"
        )


class ScheduleSettings(models.Model):
    """Work hours and health-break parameters for one user."""
    THEME_CHOICES = [
        ('dark', 'Dark'),
        ('light', 'Light'),
    ]

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='schedule_settings',
    )
    work_start_hour = models.PositiveSmallIntegerField(default=9)
    work_end_hour = models.PositiveSmallIntegerField(default=17)
    focus_block_max_hours = models.FloatField(default=2.0)
    break_interval_minutes = models.PositiveIntegerField(default=90)
    lunch_duration_minutes = models.PositiveIntegerField(default=60)
    lunch_hour = models.PositiveSmallIntegerField(default=13)
    theme = models.CharField(
        max_length=10,
        choices=THEME_CHOICES,
        default='dark',
        help_text='UI color theme.',
    )

    class Meta:
        verbose_name_plural = 'Schedule settings'

    def __str__(self):
        return f"Work {self.work_start_hour}:00–{self.work_end_hour}:00"

    @classmethod
    def get_for_user(cls, user):
        obj, _ = cls.objects.get_or_create(
            user=user,
            defaults={
                'work_start_hour': 9,
                'work_end_hour': 17,
                'focus_block_max_hours': 2.0,
                'break_interval_minutes': 90,
                'lunch_duration_minutes': 60,
                'lunch_hour': 13,
                'theme': 'dark',
            },
        )
        return obj


class WhatsAppNotificationState(models.Model):
    """Stores last notified schedule event so we only send when the event changes."""
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='whatsapp_notification_state',
    )
    last_event_key = models.CharField(max_length=256, blank=True)
    last_sent_at = models.DateTimeField(null=True, blank=True)
    last_mqtt_ok = models.BooleanField(null=True, blank=True, help_text="True=last publish succeeded, False=failed, null=never tried")
    last_mqtt_checked_at = models.DateTimeField(null=True, blank=True, help_text="When we last attempted MQTT publish")
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name_plural = "WhatsApp notification state"

    @classmethod
    def get_for_user(cls, user):
        obj, _ = cls.objects.get_or_create(user=user)
        return obj


class GoogleCalendarConnection(models.Model):
    """Per-user OAuth credentials for Google Calendar sync."""
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='google_calendar',
    )
    token_json = models.TextField(blank=True, help_text="OAuth token JSON (includes refresh token)")
    calendar_id = models.CharField(max_length=256, default='primary')
    sync_enabled = models.BooleanField(default=True)
    sync_breaks = models.BooleanField(
        default=True,
        help_text="Also push lunch/health breaks as calendar events",
    )
    pull_enabled = models.BooleanField(
        default=True,
        help_text="Automatically pull Google Calendar events into this app as busy time.",
    )
    last_synced_at = models.DateTimeField(null=True, blank=True)
    last_sync_ok = models.BooleanField(null=True, blank=True)
    last_sync_error = models.TextField(blank=True)
    last_pulled_at = models.DateTimeField(null=True, blank=True)
    last_pull_ok = models.BooleanField(null=True, blank=True)
    last_pull_error = models.TextField(blank=True)
    connected_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name_plural = "Google Calendar connections"

    def __str__(self):
        return f"Google Calendar for {self.user}"

    @property
    def is_connected(self):
        return bool(self.token_json.strip())


class CalendarEventMapping(models.Model):
    """Maps a local schedule slot to a Google Calendar event id."""
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='calendar_event_mappings',
    )
    schedule_date = models.DateField()
    local_key = models.CharField(max_length=256)
    google_event_id = models.CharField(max_length=256)
    content_hash = models.CharField(
        max_length=64,
        blank=True,
        help_text="Hash of last synced event body; skip API when unchanged.",
    )
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = [('user', 'schedule_date', 'local_key')]
        indexes = [
            models.Index(fields=['user', 'schedule_date']),
        ]

    def __str__(self):
        return f"{self.local_key} → {self.google_event_id}"


class ImportedCalendarEvent(models.Model):
    """External Google Calendar event treated as busy time in this app."""
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='imported_calendar_events',
    )
    google_event_id = models.CharField(max_length=256)
    calendar_id = models.CharField(max_length=256, default='primary')
    summary = models.CharField(max_length=500, blank=True)
    description = models.TextField(blank=True)
    start_at = models.DateTimeField()
    end_at = models.DateTimeField()
    is_all_day = models.BooleanField(default=False)
    status = models.CharField(max_length=32, default='confirmed')
    schedule_date = models.DateField(
        help_text="Local calendar date (app timezone) for day queries.",
    )
    etag = models.CharField(max_length=128, blank=True)
    content_hash = models.CharField(max_length=64, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = [('user', 'google_event_id')]
        indexes = [
            models.Index(fields=['user', 'schedule_date']),
            models.Index(fields=['user', 'start_at']),
        ]
        ordering = ['start_at']

    def __str__(self):
        return f"{self.summary or self.google_event_id} @ {self.schedule_date}"
