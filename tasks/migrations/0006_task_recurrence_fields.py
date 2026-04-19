from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("tasks", "0005_task_starts_on"),
    ]

    operations = [
        migrations.AddField(
            model_name="task",
            name="recurrence_every",
            field=models.PositiveIntegerField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="task",
            name="recurrence_unit",
            field=models.CharField(
                blank=True,
                choices=[
                    ("daily", "Daily"),
                    ("weekly", "Weekly"),
                    ("monthly", "Monthly"),
                    ("yearly", "Yearly"),
                ],
                max_length=20,
                null=True,
            ),
        ),
        migrations.AddField(
            model_name="task",
            name="schedule_type",
            field=models.CharField(
                choices=[("one_time", "One time"), ("recurring", "Recurring")],
                default="one_time",
                max_length=20,
            ),
        ),
    ]
