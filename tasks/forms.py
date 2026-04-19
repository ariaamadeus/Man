from django import forms
from django.core.exceptions import ValidationError

from .models import Task, ScheduleSettings


class TaskForm(forms.ModelForm):
    class Meta:
        model = Task
        fields = [
            'name', 'duration_minutes', 'priority', 'task_type',
            'schedule_type', 'recurrence_unit', 'recurrence_every',
            'starts_on', 'deadline', 'description',
        ]
        widgets = {
            'name': forms.TextInput(attrs={'class': 'form-input', 'placeholder': 'Task name'}),
            'duration_minutes': forms.NumberInput(attrs={'class': 'form-input', 'min': 5, 'step': 5}),
            'priority': forms.Select(attrs={'class': 'form-select'}),
            'task_type': forms.Select(attrs={'class': 'form-select'}),
            'schedule_type': forms.Select(attrs={'class': 'form-select'}),
            'recurrence_unit': forms.Select(attrs={'class': 'form-select'}),
            'recurrence_every': forms.NumberInput(attrs={'class': 'form-input', 'min': 1, 'step': 1}),
            'starts_on': forms.DateInput(attrs={'class': 'form-input custom-date-picker', 'type': 'date', 'readonly': True}),
            'deadline': forms.DateInput(attrs={'class': 'form-input custom-date-picker', 'type': 'date', 'readonly': True}),
            'description': forms.Textarea(attrs={'class': 'form-textarea', 'rows': 2, 'placeholder': 'Optional description'}),
        }

    def clean(self):
        cleaned = super().clean()
        schedule_type = cleaned.get('schedule_type')
        recurrence_unit = cleaned.get('recurrence_unit')
        recurrence_every = cleaned.get('recurrence_every')
        starts_on = cleaned.get('starts_on')
        deadline = cleaned.get('deadline')

        if schedule_type == 'recurring':
            if not recurrence_unit:
                self.add_error('recurrence_unit', 'Please choose how often this task repeats.')
            if recurrence_every is None:
                self.add_error('recurrence_every', 'Please enter how many units between repeats.')
            elif recurrence_every < 1:
                self.add_error('recurrence_every', 'Value must be at least 1.')
        else:
            cleaned['recurrence_unit'] = None
            cleaned['recurrence_every'] = None

        if starts_on and deadline and starts_on > deadline:
            raise ValidationError({
                'starts_on': ['Start date cannot be after the deadline.'],
            })
        return cleaned


class ScheduleSettingsForm(forms.ModelForm):
    class Meta:
        model = ScheduleSettings
        fields = [
            'work_start_hour', 'work_end_hour',
            'focus_block_max_hours', 'break_interval_minutes',
            'lunch_duration_minutes', 'lunch_hour',
        ]
        widgets = {
            'work_start_hour': forms.NumberInput(attrs={'class': 'form-input', 'min': 0, 'max': 23}),
            'work_end_hour': forms.NumberInput(attrs={'class': 'form-input', 'min': 0, 'max': 23}),
            'focus_block_max_hours': forms.NumberInput(attrs={'class': 'form-input', 'min': 0.5, 'step': 0.5}),
            'break_interval_minutes': forms.NumberInput(attrs={'class': 'form-input', 'min': 15}),
            'lunch_duration_minutes': forms.NumberInput(attrs={'class': 'form-input', 'min': 15}),
            'lunch_hour': forms.NumberInput(attrs={'class': 'form-input', 'min': 0, 'max': 23}),
        }
