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

    name = models.CharField(max_length=200)
    duration_minutes = models.PositiveIntegerField()
    priority = models.CharField(max_length=10, choices=PRIORITY_CHOICES, default='medium')
    task_type = models.CharField(max_length=20, choices=TASK_TYPE_CHOICES, default='focus')
    deadline = models.DateField(null=True, blank=True)
    description = models.TextField(blank=True)
    completed = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return self.name


class ScheduleSettings(models.Model):
    """Singleton-style settings for work hours and health breaks."""
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
    def get_settings(cls):
        obj = cls.objects.first()
        if obj is None:
            obj = cls.objects.create()
        return obj
