from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ('tasks', '0012_schedule_settings_theme'),
    ]

    operations = [
        migrations.AddField(
            model_name='googlecalendarconnection',
            name='pull_enabled',
            field=models.BooleanField(
                default=True,
                help_text='Automatically pull Google Calendar events into this app as busy time.',
            ),
        ),
        migrations.AddField(
            model_name='googlecalendarconnection',
            name='last_pulled_at',
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name='googlecalendarconnection',
            name='last_pull_ok',
            field=models.BooleanField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name='googlecalendarconnection',
            name='last_pull_error',
            field=models.TextField(blank=True),
        ),
        migrations.CreateModel(
            name='ImportedCalendarEvent',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('google_event_id', models.CharField(max_length=256)),
                ('calendar_id', models.CharField(default='primary', max_length=256)),
                ('summary', models.CharField(blank=True, max_length=500)),
                ('description', models.TextField(blank=True)),
                ('start_at', models.DateTimeField()),
                ('end_at', models.DateTimeField()),
                ('is_all_day', models.BooleanField(default=False)),
                ('status', models.CharField(default='confirmed', max_length=32)),
                ('schedule_date', models.DateField(help_text='Local calendar date (app timezone) for day queries.')),
                ('etag', models.CharField(blank=True, max_length=128)),
                ('content_hash', models.CharField(blank=True, max_length=64)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('user', models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='imported_calendar_events',
                    to=settings.AUTH_USER_MODEL,
                )),
            ],
            options={
                'ordering': ['start_at'],
                'unique_together': {('user', 'google_event_id')},
                'indexes': [
                    models.Index(fields=['user', 'schedule_date'], name='tasks_impor_user_id_sched_idx'),
                    models.Index(fields=['user', 'start_at'], name='tasks_impor_user_id_start_idx'),
                ],
            },
        ),
    ]
