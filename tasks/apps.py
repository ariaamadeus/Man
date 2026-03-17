from __future__ import annotations

import logging
import os
import sys
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


def _should_autostart_in_this_process() -> bool:
    """
    On Windows/Django runserver, the auto-reloader spawns an extra process.
    Only start background threads in the real serving process.
    """
    if not getattr(settings, "MQTT_NOTIFIER_AUTOSTART", False):
        return False
    if "runserver" not in sys.argv:
        return False
    # In DEBUG, only start in the auto-reloader's main process.
    if getattr(settings, "DEBUG", False):
        return os.environ.get("RUN_MAIN") == "true"
    return True


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

    if getattr(settings, "MQTT_PUBLISH_STARTUP_STATUS", True):
        def _publish_startup_once() -> None:
            try:
                # Slight delay so DB is ready (and migrations complete).
                time.sleep(1)
                from django.utils import timezone
                from .models import WhatsAppNotificationState
                from .whatsapp import publish_startup_status_and_confirm

                ok = publish_startup_status_and_confirm()
                state = WhatsAppNotificationState.get_state()
                state.last_mqtt_ok = ok
                state.last_mqtt_checked_at = timezone.now()
                state.save()
                logger.info("Published MQTT startup status ok=%s", ok)
            except Exception:
                logger.exception("Failed to publish MQTT startup status")

        threading.Thread(
            target=_publish_startup_once,
            name="mqtt-startup-status",
            daemon=True,
        ).start()


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

        # Also start immediately on boot (no request needed) in the real runserver process.
        # This makes the MQTT startup status publish happen as soon as the server is up.
        if _should_autostart_in_this_process():
            _start_notifier_if_needed()

