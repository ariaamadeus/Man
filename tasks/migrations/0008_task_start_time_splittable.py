from django.db import migrations, models


def mark_meetings_unsplittable(apps, schema_editor):
    Task = apps.get_model("tasks", "Task")
    Task.objects.filter(task_type="meeting").update(splittable=False)


def noop_reverse(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ("tasks", "0007_google_calendar"),
    ]

    operations = [
        migrations.AddField(
            model_name="task",
            name="start_time",
            field=models.TimeField(
                blank=True,
                help_text="If set, the scheduler will try to place this task at this clock time.",
                null=True,
            ),
        ),
        migrations.AddField(
            model_name="task",
            name="splittable",
            field=models.BooleanField(
                default=True,
                help_text="If false, health breaks will not split this task into multiple blocks.",
            ),
        ),
        migrations.RunPython(mark_meetings_unsplittable, noop_reverse),
    ]
