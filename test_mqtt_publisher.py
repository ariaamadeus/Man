"""
Standalone MQTT publish test script.

Loads MQTT settings from .env (via python-dotenv) and publishes a test message.

Usage:
  python test_mqtt_publisher.py
  python test_mqtt_publisher.py --message "hello" --topic "man/schedule/current"
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path

import paho.mqtt.client as mqtt
from dotenv import load_dotenv


def _get_env_int(name: str, default: int) -> int:
    raw = os.environ.get(name, "").strip()
    if not raw:
        return default
    try:
        return int(raw)
    except ValueError:
        raise SystemExit(f"Invalid {name}={raw!r}; expected an integer")


def main() -> int:
    parser = argparse.ArgumentParser(description="Publish a test MQTT message using .env settings.")
    parser.add_argument("--broker", default=None, help="MQTT broker host (default: MQTT_BROKER or localhost)")
    parser.add_argument("--port", type=int, default=None, help="MQTT broker port (default: MQTT_PORT or 1883)")
    parser.add_argument("--topic", default=None, help="MQTT topic (default: MQTT_TOPIC or man/schedule/current)")
    parser.add_argument("--message", default=None, help="Message string to publish (default: JSON payload)")
    parser.add_argument("--qos", type=int, default=None, choices=[0, 1, 2], help="QoS (default: 1)")
    parser.add_argument("--retain", action="store_true", help="Publish with retain flag")
    parser.add_argument("--timeout", type=int, default=10, help="Connect/publish timeout seconds (default: 10)")
    args = parser.parse_args()

    repo_root = Path(__file__).resolve().parent
    load_dotenv(repo_root / ".env")

    broker = (args.broker or os.environ.get("MQTT_BROKER", "").strip() or "localhost")
    port = args.port if args.port is not None else _get_env_int("MQTT_PORT", 1883)
    topic = (args.topic or os.environ.get("MQTT_TOPIC", "").strip() or "man/schedule/current")
    username = os.environ.get("MQTT_USERNAME", "").strip()
    password = os.environ.get("MQTT_PASSWORD", "").strip()
    qos = args.qos if args.qos is not None else 1

    if args.message is not None:
        payload = args.message
    else:
        payload = json.dumps(
            {
                "source": "test_mqtt_publisher.py",
                "ts": int(time.time()),
                "message": "Hello from Man",
            },
            ensure_ascii=False,
        )

    print(f"Broker:   {broker}:{port}")
    print(f"Topic:    {topic}")
    print(f"QoS:      {qos}  Retain: {args.retain}")
    print(f"Auth:     {'yes' if username else 'no'}")
    print(f"Payload:  {payload}")

    client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
    if username:
        client.username_pw_set(username, password or None)

    # Connect + publish (blocking) with a hard timeout.
    try:
        client.connect(broker, port=port, keepalive=60)
    except Exception as e:
        print(f"\nERROR: connect failed: {e}", file=sys.stderr)
        return 2

    try:
        info = client.publish(topic, payload, qos=qos, retain=args.retain)
        info.wait_for_publish(timeout=args.timeout)
    except Exception as e:
        print(f"\nERROR: publish failed: {e}", file=sys.stderr)
        try:
            client.disconnect()
        except Exception:
            pass
        return 3

    try:
        client.disconnect()
    except Exception:
        pass

    if info.rc != mqtt.MQTT_ERR_SUCCESS:
        print(f"\nERROR: publish returned rc={info.rc}", file=sys.stderr)
        return 4

    if not info.is_published():
        print("\nERROR: publish did not complete within timeout", file=sys.stderr)
        return 5

    print("\nOK: published successfully")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

