from django.conf import settings
from django.db import models


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

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='tasks',
    )
    name = models.CharField(max_length=200)
    duration_minutes = models.PositiveIntegerField()
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
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']

    def save(self, *args, **kwargs):
        # Meetings must stay contiguous (cannot be split around breaks).
        if self.task_type == 'meeting':
            self.splittable = False
        super().save(*args, **kwargs)

    def __str__(self):
        return self.name


class ScheduleSettings(models.Model):
    """Work hours and health-break parameters for one user."""
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
    last_synced_at = models.DateTimeField(null=True, blank=True)
    last_sync_ok = models.BooleanField(null=True, blank=True)
    last_sync_error = models.TextField(blank=True)
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
