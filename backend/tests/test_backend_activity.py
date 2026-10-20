from __future__ import annotations

import json
import sqlite3
import time
import unittest
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import app as backend_app
from activity_recognition import ActivityRecognizer
from inference_service import InferenceService
from test_activity_recognition import reading


class StubInferenceService:
    def __init__(self, status: str = "running", model_loaded: bool = True) -> None:
        self._status = {
            "status": status,
            "model_loaded": model_loaded,
            "model_version": "corrected-test-model",
            "queue_depth": 0,
            "queue_capacity": 100,
            "dropped_samples": 0,
            "inference_errors": 0,
            "last_error": None,
        }

    def status(self):
        return dict(self._status)

    def offer(self, _reading):
        return True


def sensor_payload(device_id: str = "test-device") -> dict[str, object]:
    return {
        "device_id": device_id,
        "timestamp": datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z"),
        "accel_m_s2": {"x": 0.0, "y": 0.0, "z": 9.48},
        "gyro_rad_s": {"x": 0.01, "y": -0.008, "z": 0.004},
    }


def prediction(
    device_id: str,
    label: str = "IDLE",
    code: int = 0,
    end: datetime | None = None,
) -> dict[str, object]:
    end = end or datetime.now(timezone.utc)
    start = end - timedelta(seconds=1.8)
    return {
        "device_id": device_id,
        "activity_label": label,
        "activity_code": code,
        "detection_method": "RULE_BASED" if label == "IDLE" else "DECISION_TREE",
        "model_version": "corrected-test-model",
        "window_start_timestamp": start.isoformat(timespec="milliseconds").replace("+00:00", "Z"),
        "window_end_timestamp": end.isoformat(timespec="milliseconds").replace("+00:00", "Z"),
        "experimental": True,
    }


class BackendActivityTests(unittest.TestCase):
    def setUp(self) -> None:
        self.db_uri = f"file:activity-test-{uuid.uuid4().hex}?mode=memory&cache=shared"
        self.db_path = self.db_uri
        self.keeper_connection = sqlite3.connect(self.db_uri, uri=True)
        backend_app.initialize_database(self.db_path)
        self.db_patch = patch.object(backend_app, "DB_PATH", self.db_path)
        self.db_patch.start()
        self.inference_patch = patch.object(
            backend_app, "inference_service", StubInferenceService()
        )
        self.inference_patch.start()
        backend_app.app.testing = True
        self.client = backend_app.app.test_client()

    def tearDown(self) -> None:
        self.inference_patch.stop()
        self.db_patch.stop()
        self.keeper_connection.close()

    def insert_reading(self, device_id: str = "test-device") -> None:
        normalized = backend_app.validate_reading(sensor_payload(device_id))
        backend_app.store_reading(normalized, self.db_path)

    def count_rows(self, table: str) -> int:
        connection = sqlite3.connect(self.db_uri, uri=True)
        try:
            return connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
        finally:
            connection.close()

    def test_additive_database_initialization_preserves_raw_readings(self) -> None:
        self.insert_reading()
        before = self.count_rows("sensor_readings")
        backend_app.initialize_database(self.db_path)
        self.assertEqual(self.count_rows("sensor_readings"), before)
        connection = sqlite3.connect(self.db_uri, uri=True)
        try:
            table = connection.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name='activity_predictions'"
            ).fetchone()
        finally:
            connection.close()
        self.assertIsNotNone(table)

    def test_prediction_insert_is_separate_and_duplicate_safe(self) -> None:
        self.insert_reading()
        raw_before = self.count_rows("sensor_readings")
        item = prediction("test-device")
        self.assertTrue(backend_app.store_activity_prediction(item, self.db_path))
        self.assertFalse(backend_app.store_activity_prediction(item, self.db_path))
        self.assertEqual(self.count_rows("activity_predictions"), 1)
        self.assertEqual(self.count_rows("sensor_readings"), raw_before)

    def test_real_corrected_model_worker_persists_experimental_windows(self) -> None:
        service = InferenceService(
            ActivityRecognizer.load_corrected,
            lambda item: backend_app.store_activity_prediction(item, self.db_uri),
        )
        self.assertTrue(service.start())
        try:
            for index in range(15):
                self.assertTrue(service.offer(reading("worker-device", index)))
            deadline = time.monotonic() + 5
            while service.status()["predictions_stored"] < 2 and time.monotonic() < deadline:
                time.sleep(0.01)
            self.assertEqual(service.status()["predictions_stored"], 2)
            predictions = backend_app._query_activity_predictions(10, "worker-device", self.db_uri)
            self.assertEqual(len(predictions), 2)
            self.assertTrue(all(item["activity_label"] == "IDLE" for item in predictions))
            self.assertTrue(all(item["experimental"] for item in predictions))
        finally:
            self.assertTrue(service.stop())

    def test_activity_latest_reports_prediction_and_experimental_status(self) -> None:
        item = prediction("test-device", "WALKING", 1)
        self.assertTrue(backend_app.store_activity_prediction(item, self.db_path))
        response = self.client.get("/api/activity/latest?device_id=test-device")
        self.assertEqual(response.status_code, 200)
        body = response.get_json()
        self.assertEqual(body["status"], "available")
        self.assertEqual(body["current_activity"], "WALKING")
        self.assertFalse(body["is_stale"])
        self.assertTrue(body["prediction"]["experimental"])
        self.assertEqual(body["prediction"]["detection_method"], "DECISION_TREE")

    def test_no_predictions_returns_unavailable_or_pending_not_an_activity(self) -> None:
        response = self.client.get("/api/activity/latest")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json()["status"], "unavailable")
        self.assertIsNone(response.get_json()["current_activity"])
        self.insert_reading()
        response = self.client.get("/api/activity/latest")
        self.assertEqual(response.get_json()["status"], "pending")
        self.assertIsNone(response.get_json()["current_activity"])

    def test_stale_prediction_is_never_returned_as_current(self) -> None:
        self.insert_reading()
        old_end = datetime.now(timezone.utc) - timedelta(seconds=20)
        item = prediction("test-device", "RUNNING", 2, end=old_end)
        self.assertTrue(backend_app.store_activity_prediction(item, self.db_path))
        response = self.client.get("/api/activity/latest")
        body = response.get_json()
        self.assertEqual(body["status"], "pending")
        self.assertTrue(body["is_stale"])
        self.assertIsNone(body["current_activity"])

    def test_missing_model_is_reported_as_unavailable(self) -> None:
        self.insert_reading()
        unavailable = StubInferenceService(status="unavailable", model_loaded=False)
        unavailable._status["last_error"] = "model load failed"
        with patch.object(backend_app, "inference_service", unavailable):
            response = self.client.get("/api/activity/latest")
        body = response.get_json()
        self.assertEqual(body["status"], "unavailable")
        self.assertIsNone(body["current_activity"])
        self.assertIn("model load failed", body["reason"])

    def test_history_filter_empty_and_invalid_queries(self) -> None:
        self.assertTrue(backend_app.store_activity_prediction(prediction("device-a"), self.db_path))
        self.assertTrue(backend_app.store_activity_prediction(prediction("device-b"), self.db_path))
        response = self.client.get("/api/activity/history?limit=10&device_id=device-a")
        self.assertEqual(response.status_code, 200)
        body = response.get_json()
        self.assertEqual(body["count"], 1)
        self.assertEqual(body["predictions"][0]["device_id"], "device-a")
        self.assertTrue(body["predictions"][0]["experimental"])
        self.assertEqual(self.client.get("/api/activity/history?limit=0").status_code, 400)
        self.assertEqual(self.client.get("/api/activity/latest?device_id=%20").status_code, 400)

    def test_existing_raw_apis_remain_available(self) -> None:
        self.insert_reading()
        latest = self.client.get("/api/latest")
        history = self.client.get("/api/history?limit=5")
        self.assertEqual(latest.status_code, 200)
        self.assertEqual(latest.get_json()["reading"]["device_id"], "test-device")
        self.assertEqual(history.get_json()["count"], 1)

    def test_health_keeps_mqtt_status_and_exposes_inference_status(self) -> None:
        backend_app._mqtt_connected.set()
        try:
            response = self.client.get("/health")
        finally:
            backend_app._mqtt_connected.clear()
        body = response.get_json()
        self.assertEqual(response.status_code, 200)
        self.assertTrue(body["mqtt_connected"])
        self.assertEqual(body["mqtt_topic"], backend_app.TOPIC)
        self.assertEqual(body["activity_inference"]["status"], "running")

    def test_database_failure_is_reported_by_activity_api(self) -> None:
        broken_path = Path(__file__).resolve().parent / ".missing-parent" / "db.sqlite"
        with patch.object(backend_app, "DB_PATH", broken_path):
            with self.assertLogs("lab3", level="ERROR"):
                response = self.client.get("/api/activity/history")
        self.assertEqual(response.status_code, 503)
        self.assertEqual(response.get_json()["error"], "activity database unavailable")

    def test_mqtt_callback_keeps_raw_storage_when_inference_enqueue_fails(self) -> None:
        class BrokenInference:
            discontinuity_marked = False

            def offer(self, _reading):
                raise RuntimeError("controlled queue failure")

            def mark_discontinuity(self):
                self.discontinuity_marked = True

        payload = json.dumps(sensor_payload("callback-device")).encode("utf-8")
        message = SimpleNamespace(topic=backend_app.TOPIC, payload=payload)
        broken_inference = BrokenInference()
        with patch.object(backend_app, "inference_service", broken_inference):
            with self.assertLogs("lab3", level="ERROR"):
                backend_app._on_message(None, None, message)
        self.assertEqual(self.count_rows("sensor_readings"), 1)
        self.assertEqual(self.count_rows("activity_predictions"), 0)
        self.assertTrue(broken_inference.discontinuity_marked)


if __name__ == "__main__":
    unittest.main()
