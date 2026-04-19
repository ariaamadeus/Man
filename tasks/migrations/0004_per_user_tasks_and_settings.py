# Generated manually for per-account schedules

from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


def assign_existing_data_to_user(apps, schema_editor):
    app_label, model_name = settings.AUTH_USER_MODEL.split(".")
    User = apps.get_model(app_label, model_name)
    Task = apps.get_model("tasks", "Task")
    ScheduleSettings = apps.get_model("tasks", "ScheduleSettings")
    WhatsAppNotificationState = apps.get_model("tasks", "WhatsAppNotificationState")

    target = (
        User.objects.filter(is_superuser=True).order_by("pk").first()
        or User.objects.order_by("pk").first()
    )
    if not target:
        Task.objects.all().delete()
        ScheduleSettings.objects.all().delete()
        WhatsAppNotificationState.objects.all().delete()
        return

    Task.objects.filter(user__isnull=True).update(user_id=target.pk)

    orphan_settings = list(
        ScheduleSettings.objects.filter(user__isnull=True).order_by("pk")
    )
    if orphan_settings:
        primary = orphan_settings[0]
        if ScheduleSettings.objects.filter(user_id=target.pk).exists():
            for row in orphan_settings:
                row.delete()
        else:
            primary.user_id = target.pk
            primary.save(update_fields=["user_id"])
            for extra in orphan_settings[1:]:
                extra.delete()

    orphan_wa = list(
        WhatsAppNotificationState.objects.filter(user__isnull=True).order_by("pk")
    )
    if orphan_wa:
        primary = orphan_wa[0]
        if WhatsAppNotificationState.objects.filter(user_id=target.pk).exists():
            for row in orphan_wa:
                row.delete()
        else:
            primary.user_id = target.pk
            primary.save(update_fields=["user_id"])
            for extra in orphan_wa[1:]:
                extra.delete()


class Migration(migrations.Migration):

    dependencies = [
        ("tasks", "0003_mqtt_connection_status"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.AddField(
            model_name="task",
            name="user",
            field=models.ForeignKey(
                null=True,
                on_delete=django.db.models.deletion.CASCADE,
                related_name="tasks",
                to=settings.AUTH_USER_MODEL,
            ),
        ),
        migrations.AddField(
            model_name="schedulesettings",
            name="user",
            field=models.OneToOneField(
                null=True,
                on_delete=django.db.models.deletion.CASCADE,
                related_name="schedule_settings",
                to=settings.AUTH_USER_MODEL,
            ),
        ),
        migrations.AddField(
            model_name="whatsappnotificationstate",
            name="user",
            field=models.OneToOneField(
                null=True,
                on_delete=django.db.models.deletion.CASCADE,
                related_name="whatsapp_notification_state",
                to=settings.AUTH_USER_MODEL,
            ),
        ),
        migrations.RunPython(assign_existing_data_to_user, migrations.RunPython.noop),
        migrations.AlterField(
            model_name="task",
            name="user",
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.CASCADE,
                related_name="tasks",
                to=settings.AUTH_USER_MODEL,
            ),
        ),
        migrations.AlterField(
            model_name="schedulesettings",
            name="user",
            field=models.OneToOneField(
                on_delete=django.db.models.deletion.CASCADE,
                related_name="schedule_settings",
                to=settings.AUTH_USER_MODEL,
            ),
        ),
        migrations.AlterField(
            model_name="whatsappnotificationstate",
            name="user",
            field=models.OneToOneField(
                on_delete=django.db.models.deletion.CASCADE,
                related_name="whatsapp_notification_state",
                to=settings.AUTH_USER_MODEL,
            ),
        ),
    ]
