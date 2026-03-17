"""
MQTT integration. Publishes a message when the current schedule event changes.
Configure MQTT_BROKER, MQTT_TOPIC (and optionally MQTT_USERNAME, MQTT_PASSWORD) in .env.
"""
import logging
from datetime import date, datetime

import paho.mqtt.client as mqtt
from django.conf import settings

logger = logging.getLogger(__name__)


def publish_mqtt_message(text: str) -> bool:
    """
    Publish a message to the configured MQTT topic.
    Returns True if publish was successful.
    """
    broker = getattr(settings, "MQTT_BROKER", "") or ""
    topic = getattr(settings, "MQTT_TOPIC", "") or ""
    if not broker or not topic:
        logger.warning("MQTT not configured: set MQTT_BROKER and MQTT_TOPIC in .env")
        return False
    port = getattr(settings, "MQTT_PORT", 1883)
    username = getattr(settings, "MQTT_USERNAME", "") or ""
    password = getattr(settings, "MQTT_PASSWORD", "") or ""

    try:
        client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
        if username:
            client.username_pw_set(username, password or None)
        logger.info("MQTT publish attempt broker=%s port=%s topic=%s", broker, port, topic)
        client.connect(broker, port=port, keepalive=60)
        client.loop_start()
        result = client.publish(topic, text, qos=1)
        # QoS1 needs the network loop to complete the handshake.
        result.wait_for_publish(timeout=10)
        client.loop_stop()
        client.disconnect()
        if result.rc != mqtt.MQTT_ERR_SUCCESS:
            logger.warning("MQTT publish returned rc=%s", result.rc)
            return False
        if not result.is_published():
            logger.warning("MQTT publish did not complete before timeout")
            return False
        logger.info("MQTT message published to %s", topic)
        return True
    except Exception as e:
        logger.exception("MQTT publish failed: %s", e)
        return False


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
    if publish_mqtt_message(message):
        state.last_event_key = key
        state.last_sent_at = timezone.now()
        state.save()
        logger.info("Published to MQTT for new current event: %s", key)
