from django import forms
from .models import Task, ScheduleSettings


class TaskForm(forms.ModelForm):
    class Meta:
        model = Task
        fields = ['name', 'duration_minutes', 'priority', 'task_type', 'deadline', 'description']
        widgets = {
            'name': forms.TextInput(attrs={'class': 'form-input', 'placeholder': 'Task name'}),
            'duration_minutes': forms.NumberInput(attrs={'class': 'form-input', 'min': 5, 'step': 5}),
            'priority': forms.Select(attrs={'class': 'form-select'}),
            'task_type': forms.Select(attrs={'class': 'form-select'}),
            'deadline': forms.DateInput(attrs={'class': 'form-input custom-date-picker', 'type': 'date', 'readonly': True}),
            'description': forms.Textarea(attrs={'class': 'form-textarea', 'rows': 2, 'placeholder': 'Optional description'}),
        }


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
