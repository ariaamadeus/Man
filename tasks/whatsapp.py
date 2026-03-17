"""
MQTT integration. Publishes a message when the current schedule event changes.
Configure MQTT_BROKER, MQTT_TOPIC (and optionally MQTT_USERNAME, MQTT_PASSWORD) in .env.
"""
import logging
from datetime import date, datetime

import requests
from django.conf import settings

logger = logging.getLogger(__name__)


def _adafruit_http_publish(value: str, *, topic_override: str | None = None, timeout_seconds: int = 10) -> bool:
    """
    Publish to Adafruit IO via HTTPS (works on hosts that block MQTT ports, like PythonAnywhere).

    Matches:
      curl -F "value=..." -H "X-AIO-Key: <key>" https://io.adafruit.com/api/v2/<topic>/data

    Where <topic> is something like: "{username}/feeds/{feed_key}"
    """
    topic = (topic_override or getattr(settings, "MQTT_TOPIC", "") or "").strip()
    aio_key = (getattr(settings, "MQTT_PASSWORD", "") or "").strip()
    if not topic or not aio_key:
        logger.warning("Adafruit IO not configured: set MQTT_TOPIC and MQTT_PASSWORD in .env")
        return False

    url = f"https://io.adafruit.com/api/v2/{topic}/data"
    try:
        resp = requests.post(
            url,
            headers={"X-AIO-Key": aio_key},
            files={"value": (None, value)},
            timeout=timeout_seconds,
        )
        if 200 <= resp.status_code < 300:
            return True
        logger.warning("Adafruit IO publish failed status=%s body=%s", resp.status_code, resp.text[:300])
        return False
    except Exception as e:
        logger.exception("Adafruit IO publish exception: %s", e)
        return False


# Backwards-compatible name used across the app; now publishes via HTTPS to Adafruit IO.
def publish_mqtt_message(text: str, *, topic_override: str | None = None, retain: bool = True) -> bool:
    _ = retain  # retain is not supported via Adafruit IO HTTP API
    return _adafruit_http_publish(text, topic_override=topic_override)


def publish_startup_status() -> bool:
    """
    Publish a one-time startup status message so subscribers immediately know the server is online.
    """
    topic = getattr(settings, "MQTT_STARTUP_STATUS_TOPIC", "") or ""
    if not topic:
        # Default to MQTT_TOPIC to stay compatible with brokers like Adafruit IO
        # that only allow publishing to specific feed topics.
        topic = getattr(settings, "MQTT_TOPIC", "") or ""
    if not topic:
        logger.warning("MQTT startup status not configured: set MQTT_TOPIC (or MQTT_STARTUP_STATUS_TOPIC)")
        return False
    return publish_mqtt_message("online", topic_override=topic, retain=True)


def publish_startup_status_and_confirm() -> bool:
    """
    With HTTPS publishing we can't "subscribe to confirm" like MQTT.
    We treat a successful HTTP 2xx response as "connected".
    """
    return publish_startup_status()


def get_mqtt_status():
    """
    Return MQTT connection status for display (e.g. in settings).
    Returns dict: configured (bool), last_ok (bool|None), last_checked_at (datetime|None), broker (str), topic (str).
    """
    from django.conf import settings
    broker = getattr(settings, "MQTT_BROKER", "") or ""
    topic = getattr(settings, "MQTT_TOPIC", "") or ""
    configured = bool(broker and topic)
    last_ok = None
    last_checked_at = None
    if configured:
        from .models import WhatsAppNotificationState
        state = WhatsAppNotificationState.get_state()
        last_ok = state.last_mqtt_ok
        last_checked_at = state.last_mqtt_checked_at
    return {
        "configured": configured,
        "last_ok": last_ok,
        "last_checked_at": last_checked_at,
        "broker": broker,
        "topic": topic,
    }


def get_current_event(schedule_date: date, schedule_items: list, now: datetime):
    """
    Return the schedule item that contains `now` (current event), or None.
    Each item has start_time, end_time (datetimes) and is_break, task_name, etc.
    """
    for item in schedule_items:
        start = item["start_time"]
        end = item["end_time"]
        if start <= now <= end:
            return item
    return None


def event_to_message(item: dict) -> str:
    """Format the current event as a short WhatsApp message."""
    start = item["start_time"]
    end = item["end_time"]
    time_range = f"{start.strftime('%H:%M')} – {end.strftime('%H:%M')}"
    if item.get("is_break"):
        break_type = item.get("break_type", "break")
        label = {
            "physical": "Break",
            "mental": "Mental break",
            "hydration": "Hydration",
            "meal": "Lunch",
        }.get(break_type, "Break")
        desc = item.get("break_description", "")
        return f"Schedule – {time_range}\n{label}{(': ' + desc if desc else '')}"
    name = item.get("task_name", "Task")
    desc = item.get("task_description", "")
    return f"Schedule – {time_range}\nNow: {name}{(' – ' + desc if desc else '')}"


def event_key(item: dict) -> str:
    """Unique key for this event so we can detect when the current event changes."""
    start = item["start_time"]
    end = item["end_time"]
    if item.get("is_break"):
        label = f"break_{item.get('break_type', '')}"
    else:
        label = item.get("task_name", "task")
    return f"{start.isoformat()}_{end.isoformat()}_{label}"


def check_and_notify_current_event():
    """
    Build today's schedule, find the current event, and publish to MQTT
    only when the current event has changed since the last notification.
    Call this from a cron job every 1–5 minutes.
    """
    from django.utils import timezone
    from .models import Task, ScheduleSettings, WhatsAppNotificationState
    from .services import build_schedule

    # Use naive datetime to match schedule items from task_manager
    now = datetime.now()
    today = date.today()
    tasks = Task.objects.all()
    schedule_settings = ScheduleSettings.get_settings()
    if not tasks.filter(completed=False).exists():
        return
    schedule_items, _ = build_schedule(tasks, schedule_settings, schedule_date=today)
    current = get_current_event(today, schedule_items, now)
    if not current:
        return
    key = event_key(current)
    state = WhatsAppNotificationState.get_state()
    if state.last_event_key == key:
        return
    message = event_to_message(current)
    ok = publish_mqtt_message(message)
    state.last_mqtt_ok = ok
    state.last_mqtt_checked_at = timezone.now()
    if ok:
        state.last_event_key = key
        state.last_sent_at = timezone.now()
    state.save()
    if ok:
        logger.info("Published to MQTT for new current event: %s", key)
