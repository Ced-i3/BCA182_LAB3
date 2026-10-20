"""Local Flask API and MQTT-to-SQLite sensor receiver."""

from __future__ import annotations

import json
import logging
import math
import os
import sqlite3
import threading
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator

import paho.mqtt.client as mqtt
from flask import Flask, jsonify, request

from activity_recognition import ActivityRecognizer, IdleThresholds
from inference_service import InferenceService


TOPIC = "lab3/sensors/motion"
BASE_DIR = Path(__file__).resolve().parent
DB_PATH: str | Path = Path(os.environ.get("MOTION_DB_PATH", BASE_DIR / "data" / "motion.db"))
MQTT_HOST = os.environ.get("MQTT_HOST", "127.0.0.1")
MQTT_PORT = int(os.environ.get("MQTT_PORT", "1883"))
API_HOST = os.environ.get("API_HOST", "127.0.0.1")
API_PORT = int(os.environ.get("API_PORT", "5000"))


def _positive_setting(name: str, default: float) -> float:
    raw = os.environ.get(name)
    if raw is None:
        return default
    try:
        value = float(raw)
    except ValueError:
        logger.warning("Ignoring invalid %s; using default %.3f", name, default)
        return default
    if not math.isfinite(value) or value <= 0:
        logger.warning("Ignoring invalid %s; using default %.3f", name, default)
        return default
    return value


def _positive_int_setting(name: str, default: int, maximum: int) -> int:
    raw = os.environ.get(name)
    if raw is None:
        return default
    try:
        value = int(raw)
    except ValueError:
        logger.warning("Ignoring invalid %s; using default %d", name, default)
        return default
    if not 1 <= value <= maximum:
        logger.warning("Ignoring invalid %s; using default %d", name, default)
        return default
    return value


@contextmanager
def _connect_database(
    db_path: str | Path | None = None,
    timeout: float = 5.0,
) -> Iterator[sqlite3.Connection]:
    target = str(db_path if db_path is not None else DB_PATH)
    connection = sqlite3.connect(target, timeout=timeout, uri=target.startswith("file:"))
    try:
        yield connection
        connection.commit()
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger("lab3")
app = Flask(__name__)
_mqtt_connected = threading.Event()


def initialize_database(db_path: str | Path | None = None) -> None:
    target = str(db_path if db_path is not None else DB_PATH)
    if target != ":memory:" and not target.startswith("file:"):
        Path(target).parent.mkdir(parents=True, exist_ok=True)
    with _connect_database(target) as connection:
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS sensor_readings (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                device_id TEXT NOT NULL,
                timestamp TEXT NOT NULL,
                accel_x REAL NOT NULL,
                accel_y REAL NOT NULL,
                accel_z REAL NOT NULL,
                gyro_x REAL NOT NULL,
                gyro_y REAL NOT NULL,
                gyro_z REAL NOT NULL,
                received_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))
            )
            """
        )
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS activity_predictions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                device_id TEXT NOT NULL,
                activity_label TEXT NOT NULL
                    CHECK (activity_label IN ('IDLE', 'WALKING', 'RUNNING')),
                activity_code INTEGER NOT NULL CHECK (activity_code IN (0, 1, 2)),
                detection_method TEXT NOT NULL
                    CHECK (detection_method IN ('RULE_BASED', 'DECISION_TREE')),
                model_version TEXT NOT NULL,
                window_start_timestamp TEXT NOT NULL,
                window_end_timestamp TEXT NOT NULL,
                created_at TEXT NOT NULL DEFAULT
                    (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
                experimental INTEGER NOT NULL DEFAULT 1 CHECK (experimental IN (0, 1)),
                UNIQUE (device_id, model_version,
                        window_start_timestamp, window_end_timestamp)
            )
            """
        )
        connection.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_activity_predictions_device_end
            ON activity_predictions (device_id, window_end_timestamp DESC)
            """
        )


def _number(value: Any, field: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{field} must be a number")
    result = float(value)
    if not math.isfinite(result):
        raise ValueError(f"{field} must be finite")
    return result


def validate_reading(payload: Any) -> dict[str, Any]:
    if not isinstance(payload, dict):
        raise ValueError("message must be a JSON object")

    required = {"device_id", "timestamp", "accel_m_s2", "gyro_rad_s"}
    if set(payload) != required:
        raise ValueError(f"message fields must be exactly: {', '.join(sorted(required))}")

    device_id = payload["device_id"]
    if not isinstance(device_id, str) or not device_id.strip() or len(device_id) > 80:
        raise ValueError("device_id must be a non-empty string of at most 80 characters")

    timestamp = payload["timestamp"]
    if not isinstance(timestamp, str):
        raise ValueError("timestamp must be an ISO 8601 string")
    try:
        parsed = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
    except ValueError as error:
        raise ValueError("timestamp must be a valid ISO 8601 string") from error
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError("timestamp must include a timezone (use UTC)")

    axes: dict[str, float] = {}
    for group in ("accel_m_s2", "gyro_rad_s"):
        values = payload[group]
        if not isinstance(values, dict) or set(values) != {"x", "y", "z"}:
            raise ValueError(f"{group} must contain exactly x, y, and z")
        for axis in ("x", "y", "z"):
            axes[f"{group}_{axis}"] = _number(values[axis], f"{group}.{axis}")

    return {
        "device_id": device_id.strip(),
        "timestamp": parsed.isoformat(timespec="milliseconds").replace("+00:00", "Z"),
        **axes,
    }


def store_reading(reading: dict[str, Any], db_path: str | Path | None = None) -> None:
    with _connect_database(db_path, timeout=5) as connection:
        connection.execute(
            """
            INSERT INTO sensor_readings (
                device_id, timestamp, accel_x, accel_y, accel_z, gyro_x, gyro_y, gyro_z
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                reading["device_id"], reading["timestamp"],
                reading["accel_m_s2_x"], reading["accel_m_s2_y"], reading["accel_m_s2_z"],
                reading["gyro_rad_s_x"], reading["gyro_rad_s_y"], reading["gyro_rad_s_z"],
            ),
        )


def store_activity_prediction(
    prediction: dict[str, Any],
    db_path: str | Path | None = None,
) -> bool:
    """Insert an experimental prediction once; leave raw sensor rows untouched."""
    if prediction.get("activity_label") not in {"IDLE", "WALKING", "RUNNING"}:
        raise ValueError("unsupported activity label")
    expected_codes = {"IDLE": 0, "WALKING": 1, "RUNNING": 2}
    if prediction.get("activity_code") != expected_codes[prediction["activity_label"]]:
        raise ValueError("activity_code does not match activity_label")
    if prediction.get("detection_method") not in {"RULE_BASED", "DECISION_TREE"}:
        raise ValueError("unsupported detection method")
    expected_method = "RULE_BASED" if prediction["activity_label"] == "IDLE" else "DECISION_TREE"
    if prediction["detection_method"] != expected_method:
        raise ValueError("detection_method does not match activity_label")
    if not prediction.get("experimental", False):
        raise ValueError("all hardware-facing predictions must remain experimental")
    with _connect_database(db_path, timeout=5) as connection:
        cursor = connection.execute(
            """
            INSERT OR IGNORE INTO activity_predictions (
                device_id, activity_label, activity_code, detection_method,
                model_version, window_start_timestamp, window_end_timestamp, experimental
            ) VALUES (?, ?, ?, ?, ?, ?, ?, 1)
            """,
            (
                prediction["device_id"], prediction["activity_label"],
                prediction["activity_code"], prediction["detection_method"],
                prediction["model_version"], prediction["window_start_timestamp"],
                prediction["window_end_timestamp"],
            ),
        )
        return cursor.rowcount == 1


def _row_to_reading(row: sqlite3.Row) -> dict[str, Any]:
    return {
        "id": row["id"],
        "device_id": row["device_id"],
        "timestamp": row["timestamp"],
        "accel_m_s2": {"x": row["accel_x"], "y": row["accel_y"], "z": row["accel_z"]},
        "gyro_rad_s": {"x": row["gyro_x"], "y": row["gyro_y"], "z": row["gyro_z"]},
        "received_at": row["received_at"],
    }


def _query_readings(
    sql: str,
    parameters: tuple[Any, ...] = (),
    db_path: str | Path | None = None,
) -> list[dict[str, Any]]:
    with _connect_database(db_path, timeout=5) as connection:
        connection.row_factory = sqlite3.Row
        rows = connection.execute(sql, parameters).fetchall()
    return [_row_to_reading(row) for row in rows]


def _row_to_prediction(row: sqlite3.Row) -> dict[str, Any]:
    return {
        "id": row["id"],
        "device_id": row["device_id"],
        "activity_label": row["activity_label"],
        "activity_code": row["activity_code"],
        "detection_method": row["detection_method"],
        "model_version": row["model_version"],
        "window_start_timestamp": row["window_start_timestamp"],
        "window_end_timestamp": row["window_end_timestamp"],
        "created_at": row["created_at"],
        "experimental": bool(row["experimental"]),
    }


def _query_activity_predictions(
    limit: int,
    device_id: str | None = None,
    db_path: str | Path | None = None,
) -> list[dict[str, Any]]:
    with _connect_database(db_path, timeout=5) as connection:
        connection.row_factory = sqlite3.Row
        if device_id is None:
            rows = connection.execute(
                "SELECT * FROM activity_predictions "
                "ORDER BY window_end_timestamp DESC, id DESC LIMIT ?",
                (limit,),
            ).fetchall()
        else:
            rows = connection.execute(
                "SELECT * FROM activity_predictions WHERE device_id = ? "
                "ORDER BY window_end_timestamp DESC, id DESC LIMIT ?",
                (device_id, limit),
            ).fetchall()
    return [_row_to_prediction(row) for row in rows]


def _query_latest_received_at(
    device_id: str | None,
    db_path: str | Path | None = None,
) -> str | None:
    with _connect_database(db_path, timeout=5) as connection:
        if device_id is None:
            row = connection.execute(
                "SELECT received_at FROM sensor_readings ORDER BY id DESC LIMIT 1"
            ).fetchone()
        else:
            row = connection.execute(
                "SELECT received_at FROM sensor_readings WHERE device_id = ? "
                "ORDER BY id DESC LIMIT 1",
                (device_id,),
            ).fetchone()
    return str(row[0]) if row else None


def _valid_device_filter() -> tuple[str | None, tuple[dict[str, str], int] | None]:
    device_id = request.args.get("device_id")
    if device_id is None:
        return None, None
    if not device_id.strip() or len(device_id) > 80:
        return None, ({"error": "device_id must contain 1 to 80 characters"}, 400)
    return device_id.strip(), None


def _parse_utc(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError("stored timestamp is not timezone-aware")
    return parsed.astimezone(timezone.utc)


ACTIVITY_QUEUE_CAPACITY = _positive_int_setting("ACTIVITY_QUEUE_CAPACITY", 100, 10000)
ACTIVITY_MAX_DEVICES = _positive_int_setting("ACTIVITY_MAX_DEVICES", 64, 256)
ACTIVITY_MAX_SAMPLE_GAP_SECONDS = _positive_setting(
    "ACTIVITY_MAX_SAMPLE_GAP_SECONDS", 0.6
)
ACTIVITY_STALE_AFTER_SECONDS = _positive_setting(
    "ACTIVITY_STALE_AFTER_SECONDS", 3.0
)


def _load_activity_recognizer() -> ActivityRecognizer:
    thresholds = IdleThresholds.from_environment()
    return ActivityRecognizer.load_corrected(thresholds=thresholds)


inference_service = InferenceService(
    recognizer_loader=_load_activity_recognizer,
    prediction_store=store_activity_prediction,
    queue_capacity=ACTIVITY_QUEUE_CAPACITY,
    max_devices=ACTIVITY_MAX_DEVICES,
    max_gap_seconds=ACTIVITY_MAX_SAMPLE_GAP_SECONDS,
)


def _on_connect(
    client: mqtt.Client,
    _userdata: Any,
    _flags: mqtt.ConnectFlags,
    reason_code: mqtt.ReasonCode,
    _properties: mqtt.Properties | None,
) -> None:
    if reason_code.is_failure:
        _mqtt_connected.clear()
        logger.error("MQTT connection refused: %s", reason_code)
        return
    _mqtt_connected.set()
    result, _mid = client.subscribe(TOPIC, qos=1)
    if result != mqtt.MQTT_ERR_SUCCESS:
        logger.error("Could not subscribe to %s (error %s)", TOPIC, result)
    else:
        logger.info("Connected to MQTT broker and subscribed to %s", TOPIC)


def _on_disconnect(
    _client: mqtt.Client,
    _userdata: Any,
    _disconnect_flags: mqtt.DisconnectFlags,
    reason_code: mqtt.ReasonCode,
    _properties: mqtt.Properties | None,
) -> None:
    _mqtt_connected.clear()
    logger.warning("MQTT disconnected (%s); automatic reconnect is enabled", reason_code)


def _mark_inference_discontinuity() -> None:
    try:
        inference_service.mark_discontinuity()
    except Exception:
        logger.exception("Could not mark an inference stream discontinuity")


def _on_message(_client: mqtt.Client, _userdata: Any, message: mqtt.MQTTMessage) -> None:
    try:
        payload = json.loads(message.payload.decode("utf-8"))
        reading = validate_reading(payload)
        store_reading(reading)
        logger.info("Stored sensor reading from %s", reading["device_id"])
        try:
            if not inference_service.offer(reading):
                logger.warning(
                    "Activity inference did not accept sample from %s; raw reading was stored",
                    reading["device_id"],
                )
        except Exception:
            logger.exception(
                "Could not enqueue activity inference for %s; raw reading was stored",
                reading["device_id"],
            )
            _mark_inference_discontinuity()
    except (UnicodeDecodeError, json.JSONDecodeError, ValueError) as error:
        _mark_inference_discontinuity()
        logger.warning("Rejected invalid MQTT message on %s: %s", message.topic, error)
    except sqlite3.Error:
        _mark_inference_discontinuity()
        logger.exception("Could not store MQTT message in SQLite")


def create_mqtt_client() -> mqtt.Client:
    client = mqtt.Client(
        callback_api_version=mqtt.CallbackAPIVersion.VERSION2,
        client_id="lab3-flask-backend",
        protocol=mqtt.MQTTv311,
    )
    client.on_connect = _on_connect
    client.on_disconnect = _on_disconnect
    client.on_message = _on_message
    client.reconnect_delay_set(min_delay=1, max_delay=30)
    return client


@app.get("/health")
def health():
    try:
        with _connect_database(timeout=2) as connection:
            connection.execute("SELECT 1").fetchone()
    except sqlite3.Error:
        logger.exception("Health check could not access SQLite")
        return jsonify({"status": "unhealthy", "mqtt_connected": _mqtt_connected.is_set()}), 503

    connected = _mqtt_connected.is_set()
    return jsonify({
        "status": "ok" if connected else "degraded",
        "mqtt_connected": connected,
        "mqtt_topic": TOPIC,
        "activity_inference": inference_service.status(),
    }), 200 if connected else 503


@app.get("/api/latest")
def latest():
    rows = _query_readings(
        "SELECT * FROM sensor_readings ORDER BY id DESC LIMIT 1"
    )
    return jsonify({"reading": rows[0] if rows else None})


@app.get("/api/history")
def history():
    raw_limit = request.args.get("limit", "20")
    try:
        limit = int(raw_limit)
    except ValueError:
        return jsonify({"error": "limit must be an integer from 1 to 100"}), 400
    if not 1 <= limit <= 100:
        return jsonify({"error": "limit must be an integer from 1 to 100"}), 400

    readings = _query_readings(
        "SELECT * FROM sensor_readings ORDER BY id DESC LIMIT ?", (limit,)
    )
    return jsonify({"readings": readings, "count": len(readings)})


@app.get("/api/activity/latest")
def activity_latest():
    device_id, error = _valid_device_filter()
    if error:
        return jsonify(error[0]), error[1]
    try:
        predictions = _query_activity_predictions(limit=1, device_id=device_id)
        latest_received_at = _query_latest_received_at(device_id)
    except sqlite3.Error:
        logger.exception("Could not query latest activity prediction")
        return jsonify({"error": "activity database unavailable"}), 503

    now = datetime.now(timezone.utc)
    prediction = predictions[0] if predictions else None
    prediction_age: float | None = None
    fresh = False
    if prediction is not None:
        try:
            created_age = (now - _parse_utc(prediction["created_at"])).total_seconds()
            window_age = (now - _parse_utc(prediction["window_end_timestamp"])).total_seconds()
            prediction_age = max(0.0, created_age, window_age)
            fresh = prediction_age <= ACTIVITY_STALE_AFTER_SECONDS
        except (TypeError, ValueError):
            logger.exception("Stored activity prediction has an invalid timestamp")

    inference_status = inference_service.status()
    input_age: float | None = None
    if latest_received_at is not None:
        try:
            input_age = max(
                0.0,
                (now - _parse_utc(latest_received_at)).total_seconds(),
            )
        except (TypeError, ValueError):
            logger.exception("Stored sensor receive timestamp is invalid")

    if fresh:
        status = "available"
        reason = None
        current_activity = prediction["activity_label"]
    elif inference_status["status"] != "running" or not inference_status["model_loaded"]:
        status = "unavailable"
        reason = inference_status.get("last_error") or "inference_service_not_running"
        current_activity = None
    elif input_age is not None and input_age <= ACTIVITY_STALE_AFTER_SECONDS:
        status = "pending"
        reason = "waiting_for_a_complete_or_fresh_window"
        current_activity = None
    else:
        status = "unavailable"
        reason = "no_recent_sensor_input"
        current_activity = None

    return jsonify({
        "status": status,
        "reason": reason,
        "device_id_filter": device_id,
        "current_activity": current_activity,
        "prediction": prediction,
        "prediction_age_seconds": prediction_age,
        "input_age_seconds": input_age,
        "is_stale": prediction is not None and not fresh,
        "stale_after_seconds": ACTIVITY_STALE_AFTER_SECONDS,
        "experimental": True,
        "inference": inference_status,
    })


@app.get("/api/activity/history")
def activity_history():
    raw_limit = request.args.get("limit", "20")
    try:
        limit = int(raw_limit)
    except ValueError:
        return jsonify({"error": "limit must be an integer from 1 to 100"}), 400
    if not 1 <= limit <= 100:
        return jsonify({"error": "limit must be an integer from 1 to 100"}), 400
    device_id, error = _valid_device_filter()
    if error:
        return jsonify(error[0]), error[1]
    try:
        predictions = _query_activity_predictions(limit=limit, device_id=device_id)
    except sqlite3.Error:
        logger.exception("Could not query activity history")
        return jsonify({"error": "activity database unavailable"}), 503
    return jsonify({
        "predictions": predictions,
        "count": len(predictions),
        "limit": limit,
        "device_id_filter": device_id,
        "experimental": True,
    })


def main() -> None:
    initialize_database()
    inference_service.start()
    client = create_mqtt_client()
    mqtt_loop_started = False
    try:
        client.connect_async(MQTT_HOST, MQTT_PORT, keepalive=30)
        client.loop_start()
        mqtt_loop_started = True
        logger.info("Starting API at http://%s:%s (SQLite: %s)", API_HOST, API_PORT, DB_PATH)
        app.run(host=API_HOST, port=API_PORT, use_reloader=False)
    finally:
        if mqtt_loop_started:
            client.disconnect()
            client.loop_stop()
        if not inference_service.stop():
            logger.error("Activity inference worker did not stop cleanly")


if __name__ == "__main__":
    main()
