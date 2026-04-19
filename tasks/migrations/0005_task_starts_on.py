from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("tasks", "0004_per_user_tasks_and_settings"),
    ]

    operations = [
        migrations.AddField(
            model_name="task",
            name="starts_on",
            field=models.DateField(
                blank=True,
                help_text="If set, this task is only included in the schedule on or after this date.",
                null=True,
            ),
        ),
    ]
