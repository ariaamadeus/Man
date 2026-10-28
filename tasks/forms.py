from django import forms
from django.core.exceptions import ValidationError

from .models import Task, ScheduleSettings


class TaskForm(forms.ModelForm):
    total_months = forms.IntegerField(
        required=False,
        min_value=0,
        initial=0,
        label='Months',
        widget=forms.NumberInput(attrs={'class': 'form-input', 'min': 0, 'step': 1, 'placeholder': '0'}),
    )
    total_days = forms.IntegerField(
        required=False,
        min_value=0,
        initial=0,
        label='Days',
        widget=forms.NumberInput(attrs={'class': 'form-input', 'min': 0, 'step': 1, 'placeholder': '0'}),
    )
    total_hours = forms.IntegerField(
        required=False,
        min_value=0,
        initial=0,
        label='Hours',
        widget=forms.NumberInput(attrs={'class': 'form-input', 'min': 0, 'step': 1, 'placeholder': '0'}),
    )
    total_mins = forms.IntegerField(
        required=False,
        min_value=0,
        initial=0,
        label='Minutes',
        widget=forms.NumberInput(attrs={'class': 'form-input', 'min': 0, 'step': 1, 'placeholder': '0'}),
    )

    class Meta:
        model = Task
        fields = [
            'name', 'duration_mode', 'duration_minutes', 'total_duration_minutes',
            'priority', 'task_type',
            'schedule_type', 'recurrence_unit', 'recurrence_every',
            'starts_on', 'start_time', 'deadline', 'description',
        ]
        widgets = {
            'name': forms.TextInput(attrs={'class': 'form-input', 'placeholder': 'Task name'}),
            'duration_mode': forms.RadioSelect(attrs={'class': 'duration-mode-radios'}),
            'duration_minutes': forms.NumberInput(attrs={
                'class': 'form-input',
                'min': 5,
                'step': 5,
                'placeholder': 'e.g. 60',
            }),
            'total_duration_minutes': forms.HiddenInput(),
            'priority': forms.Select(attrs={'class': 'form-select'}),
            'task_type': forms.Select(attrs={'class': 'form-select'}),
            'schedule_type': forms.Select(attrs={'class': 'form-select'}),
            'recurrence_unit': forms.Select(attrs={'class': 'form-select'}),
            'recurrence_every': forms.NumberInput(attrs={'class': 'form-input', 'min': 1, 'step': 1}),
            'starts_on': forms.DateInput(attrs={'class': 'form-input custom-date-picker', 'type': 'date', 'readonly': True}),
            'start_time': forms.TimeInput(attrs={'class': 'form-input', 'type': 'time'}),
            'deadline': forms.DateInput(attrs={'class': 'form-input custom-date-picker', 'type': 'date', 'readonly': True}),
            'description': forms.Textarea(attrs={'class': 'form-textarea', 'rows': 2, 'placeholder': 'Optional description'}),
        }
        labels = {
            'duration_mode': 'Duration type',
            'duration_minutes': 'Duration (minutes)',
            'total_duration_minutes': 'Total duration (minutes)',
        }
        help_texts = {
            'duration_mode': '',
            'duration_minutes': 'How long this task should take on the schedule.',
            'total_duration_minutes': '',
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Allow blank in the widget; clean() enforces the right field per mode.
        self.fields['duration_minutes'].required = False
        self.fields['total_duration_minutes'].required = False

        instance = getattr(self, 'instance', None)
        if instance and instance.pk and instance.total_duration_minutes:
            months, days, hours, minutes = Task.split_minutes(instance.total_duration_minutes)
            self.fields['total_months'].initial = months
            self.fields['total_days'].initial = days
            self.fields['total_hours'].initial = hours
            self.fields['total_mins'].initial = minutes

    def clean(self):
        cleaned = super().clean()
        schedule_type = cleaned.get('schedule_type')
        recurrence_unit = cleaned.get('recurrence_unit')
        recurrence_every = cleaned.get('recurrence_every')
        starts_on = cleaned.get('starts_on')
        deadline = cleaned.get('deadline')
        task_type = cleaned.get('task_type')
        duration_mode = cleaned.get('duration_mode') or 'per_task'
        duration_minutes = cleaned.get('duration_minutes')

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

        if duration_mode == 'total_budget':
            months = cleaned.get('total_months') or 0
            days = cleaned.get('total_days') or 0
            hours = cleaned.get('total_hours') or 0
            mins = cleaned.get('total_mins') or 0
            total = Task.combine_duration_parts(months, days, hours, mins)
            cleaned['total_duration_minutes'] = total
            if total < 5:
                raise ValidationError(
                    'Enter a total duration of at least 5 minutes '
                    '(use months, days, hours, and/or minutes).'
                )
            # Until AI allocates session chunks, use the full budget as the
            # current scheduled duration so the task still appears on the day.
            cleaned['duration_minutes'] = total
        else:
            cleaned['duration_mode'] = 'per_task'
            cleaned['total_duration_minutes'] = None
            if not duration_minutes:
                self.add_error('duration_minutes', 'Enter how long this task takes (minutes).')
            elif duration_minutes < 5:
                self.add_error('duration_minutes', 'Duration must be at least 5 minutes.')

        # Meetings are always unsplittable; applied on model save as well.
        if task_type == 'meeting':
            cleaned['splittable'] = False
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
            'break_interval_minutes': forms.NumberInput(attrs={
                'class': 'form-input',
                'min': 30,
                'step': 5,
                'title': 'Focused work minutes between breaks (minimum 30)',
            }),
            'lunch_duration_minutes': forms.NumberInput(attrs={'class': 'form-input', 'min': 15}),
            'lunch_hour': forms.NumberInput(attrs={'class': 'form-input', 'min': 0, 'max': 23}),
        }
        help_texts = {
            'break_interval_minutes': (
                'Minutes of focused work between health breaks. '
                'Minimum 30 so breaks do not stack on top of each other.'
            ),
        }

    def clean_break_interval_minutes(self):
        value = self.cleaned_data.get('break_interval_minutes')
        if value is not None and value < 30:
            raise ValidationError('Break interval must be at least 30 minutes.')
        return value

    def clean(self):
        cleaned = super().clean()
        start = cleaned.get('work_start_hour')
        end = cleaned.get('work_end_hour')
        if start is not None and end is not None and start >= end:
            raise ValidationError('Work end hour must be after work start hour.')
        return cleaned
