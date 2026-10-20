"""Publish clearly simulated six-axis motion readings over MQTT."""

from __future__ import annotations

import argparse
import json
import random
import sys
import time
from datetime import datetime, timezone

import paho.mqtt.client as mqtt


TOPIC = "lab3/sensors/motion"


def make_reading() -> dict[str, object]:
    # These values are generated for development and are not board measurements.
    return {
        "device_id": "simulator-1",
        "timestamp": datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z"),
        "accel_m_s2": {
            "x": round(random.uniform(-1.5, 1.5), 3),
            "y": round(random.uniform(-1.5, 1.5), 3),
            "z": round(9.81 + random.uniform(-1.0, 1.0), 3),
        },
        "gyro_rad_s": {
            "x": round(random.uniform(-0.8, 0.8), 3),
            "y": round(random.uniform(-0.8, 0.8), 3),
            "z": round(random.uniform(-0.8, 0.8), 3),
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Publish simulated motion readings (not RT-Spark measurements).")
    parser.add_argument("--host", default="127.0.0.1", help="MQTT broker host (default: 127.0.0.1)")
    parser.add_argument("--port", type=int, default=1883, help="MQTT broker port (default: 1883)")
    parser.add_argument("--count", type=int, default=5, help="number of simulated readings to publish")
    parser.add_argument("--interval", type=float, default=1.0, help="seconds between readings")
    args = parser.parse_args()
    if args.count < 1:
        parser.error("--count must be at least 1")
    if args.interval < 0:
        parser.error("--interval cannot be negative")

    client = mqtt.Client(
        callback_api_version=mqtt.CallbackAPIVersion.VERSION2,
        client_id="lab3-simulated-publisher",
        protocol=mqtt.MQTTv311,
    )
    try:
        client.connect(args.host, args.port, keepalive=30)
        client.loop_start()
        deadline = time.monotonic() + 5
        while not client.is_connected() and time.monotonic() < deadline:
            time.sleep(0.05)
        if not client.is_connected():
            raise TimeoutError("could not connect to MQTT broker within 5 seconds")

        for index in range(1, args.count + 1):
            reading = make_reading()
            info = client.publish(TOPIC, json.dumps(reading), qos=1)
            info.wait_for_publish(timeout=5)
            if not info.is_published():
                raise TimeoutError("MQTT publish did not complete within 5 seconds")
            print(f"Published simulated reading {index}/{args.count} to {TOPIC}")
            if index < args.count:
                time.sleep(args.interval)
    except (OSError, TimeoutError, ValueError) as error:
        print(f"Publish failed: {error}", file=sys.stderr)
        return 1
    finally:
        if client.is_connected():
            client.disconnect()
        client.loop_stop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
