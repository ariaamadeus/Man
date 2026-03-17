"""
Management command to check the current schedule event and publish to MQTT
when it changes. Run via cron every 1–5 minutes, e.g.:

  * * * * * cd /path/to/Man && python manage.py notify_current_event
"""
from django.core.management.base import BaseCommand
from tasks.whatsapp import check_and_notify_current_event


class Command(BaseCommand):
    help = "If the current schedule event has changed, publish a message to the configured MQTT topic."

    def handle(self, *args, **options):
        check_and_notify_current_event()
