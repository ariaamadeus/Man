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

import requests
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
    parser = argparse.ArgumentParser(description="Publish a test Adafruit IO message using .env settings.")
    parser.add_argument("--topic", default=None, help="Adafruit IO topic path (default: MQTT_TOPIC, e.g. username/feeds/test)")
    parser.add_argument("--message", default=None, help="Message string to publish (default: JSON payload)")
    parser.add_argument("--timeout", type=int, default=10, help="Request timeout seconds (default: 10)")
    args = parser.parse_args()

    repo_root = Path(__file__).resolve().parent
    load_dotenv(repo_root / ".env")

    topic = (args.topic or os.environ.get("MQTT_TOPIC", "").strip() or "")
    aio_key = os.environ.get("MQTT_PASSWORD", "").strip()

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

    print("Transport: HTTPS (Adafruit IO)")
    print(f"Topic:     {topic}")
    print(f"Auth:      {'yes' if aio_key else 'no'}")
    print(f"Payload:  {payload}")

    if not topic or not aio_key:
        print("\nERROR: missing MQTT_TOPIC or MQTT_PASSWORD in .env", file=sys.stderr)
        return 2

    url = f"https://io.adafruit.com/api/v2/{topic}/data"
    try:
        resp = requests.post(
            url,
            headers={"X-AIO-Key": aio_key},
            files={"value": (None, payload)},
            timeout=args.timeout,
        )
    except Exception as e:
        print(f"\nERROR: request failed: {e}", file=sys.stderr)
        return 3

    if not (200 <= resp.status_code < 300):
        print(f"\nERROR: HTTP {resp.status_code}: {resp.text}", file=sys.stderr)
        return 4

    print("\nOK: published successfully")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

