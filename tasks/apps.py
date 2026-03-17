from __future__ import annotations

import logging
import threading
import time

from django.apps import AppConfig
from django.conf import settings
from django.core.signals import request_started

logger = logging.getLogger(__name__)

_notifier_thread_started = False


def _notifier_loop(interval_seconds: int) -> None:
    # Delay a moment so startup migrations/app-loading finishes.
    time.sleep(1)
    while True:
        try:
            from .whatsapp import check_and_notify_current_event

            check_and_notify_current_event()
        except Exception:
            logger.exception("MQTT notifier loop failed")
        time.sleep(max(5, int(interval_seconds)))


def _start_notifier_if_needed(**_kwargs) -> None:
    """
    Signal handler to start the notifier thread exactly once per process.
    Must be module-level because Django signals use weakrefs by default.
    """
    global _notifier_thread_started

    if _notifier_thread_started:
        return
    if not getattr(settings, "MQTT_NOTIFIER_AUTOSTART", False):
        return

    interval = getattr(settings, "MQTT_NOTIFIER_INTERVAL_SECONDS", 60)
    t = threading.Thread(
        target=_notifier_loop,
        args=(interval,),
        name="mqtt-notifier",
        daemon=True,
    )
    t.start()
    _notifier_thread_started = True
    logger.info("Started MQTT notifier loop (interval=%ss)", interval)


class TasksConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "tasks"

    def ready(self) -> None:
        """
        Start a lightweight background notifier during `runserver` so event changes
        publish to MQTT without needing an external cron job.
        """
        # The dev server auto-reloader can create multiple processes on Windows.
        # Starting the background thread from request_started ensures it starts
        # in the actual serving process (the one receiving HTTP requests).
        request_started.connect(
            _start_notifier_if_needed,
            dispatch_uid="tasks.mqtt_notifier_autostart",
        )

