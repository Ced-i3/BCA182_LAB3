"""Cloud sync tests use disposable databases and a fake HTTPS sender."""

import sqlite3
import tempfile
import unittest
from contextlib import closing
from pathlib import Path
from unittest.mock import patch

from cloud_sync import CloudSync


class CloudSyncTests(unittest.TestCase):
    def setUp(self):
        temporary_root = Path(__file__).resolve().parents[1] / ".tmp"
        temporary_root.mkdir(exist_ok=True)
        self.tmp = tempfile.TemporaryDirectory(dir=temporary_root)
        self.addCleanup(self.tmp.cleanup)
        self.source = Path(self.tmp.name) / "source.db"
        self.state = Path(self.tmp.name) / "state.db"
        with closing(sqlite3.connect(self.source)) as db, db:
            db.executescript("""
                CREATE TABLE sensor_readings (
                    id INTEGER PRIMARY KEY, device_id TEXT, timestamp TEXT,
                    received_at TEXT, accel_x REAL, accel_y REAL, accel_z REAL,
                    gyro_x REAL, gyro_y REAL, gyro_z REAL
                );
                CREATE TABLE activity_predictions (
                    id INTEGER PRIMARY KEY, device_id TEXT, activity_label TEXT,
                    activity_code INTEGER, detection_method TEXT, model_version TEXT,
                    window_start_timestamp TEXT, window_end_timestamp TEXT,
                    created_at TEXT, experimental INTEGER
                );
            """)
        self.sent = []
        self.ok = True
        self.health_ok = True

    def worker(self):
        def send(url, token, body):
            self.sent.append(body)
            return self.ok
        def health():
            if not self.health_ok:
                raise OSError("offline")
            return {"mqtt_connected": True, "activity_inference": {
                "status": "running", "model_loaded": True}}
        return CloudSync(self.source, self.state, "rt-spark-001", "x" * 40,
                         "https://example.test/api/cloud/ingest", sender=send, health=health)

    def add_sensor(self, row_id, received="2026-10-29T08:00:00.000Z", axis=1.0):
        with closing(sqlite3.connect(self.source)) as db, db:
            db.execute("INSERT INTO sensor_readings VALUES (?,?,?,?,?,?,?,?,?,?)",
                       (row_id, "rt-spark-001", "2026-10-29T07:59:59.000Z",
                        received, axis, 2, 3, 4, 5, 6))

    def add_prediction(self):
        with closing(sqlite3.connect(self.source)) as db, db:
            db.execute("INSERT INTO activity_predictions VALUES (?,?,?,?,?,?,?,?,?,?)",
                       (7, "rt-spark-001", "WALKING", 1, "DECISION_TREE", "v1",
                        "2026-10-29T07:59:58Z", "2026-10-29T07:59:59Z",
                        "2026-10-29T08:00:00Z", 1))

    def count_outbox(self):
        with closing(sqlite3.connect(self.state)) as db:
            return db.execute("SELECT count(*) FROM outbox").fetchone()[0]

    def test_initial_sync_preserves_source_and_timestamps(self):
        self.add_sensor(1)
        self.add_prediction()
        before = self.source.read_bytes()
        self.assertEqual(self.worker().sync_once(), 2)
        self.assertEqual(self.count_outbox(), 0)
        self.assertEqual(self.sent[0]["readings"][0]["event_id"], "sensor:1")
        self.assertEqual(self.sent[0]["readings"][0]["timestamp"], "2026-10-29T07:59:59.000Z")
        self.assertEqual(self.sent[0]["predictions"][0]["event_id"], "prediction:7")
        self.assertEqual(self.source.read_bytes(), before)

    def test_failure_restart_retry_and_no_duplicate(self):
        self.add_sensor(1)
        self.ok = False
        self.assertEqual(self.worker().sync_once(), 0)
        self.assertEqual(self.count_outbox(), 1)
        self.ok = True
        self.assertEqual(self.worker().sync_once(), 1)
        self.assertEqual(self.count_outbox(), 0)
        self.assertEqual(self.worker().sync_once(), 0)
        self.assertEqual([item["readings"][0]["event_id"] for item in self.sent[:2]], ["sensor:1", "sensor:1"])

    def test_one_sample_per_receive_second(self):
        self.add_sensor(1)
        self.add_sensor(2, "2026-10-29T08:00:00.200Z")
        self.add_sensor(3, "2026-10-29T08:00:01.000Z")
        self.worker().sync_once()
        self.assertEqual([r["source_id"] for r in self.sent[0]["readings"]], [1, 3])

    def test_empty_database_sends_heartbeat(self):
        self.assertEqual(self.worker().sync_once(), 0)
        self.assertEqual(self.sent[0]["readings"], [])
        self.assertIsNone(self.sent[0]["status"]["last_sensor_received_at"])

    def test_backend_offline_heartbeat(self):
        self.health_ok = False
        self.worker().sync_once()
        self.assertFalse(self.sent[0]["status"]["backend_online"])

    def test_malformed_sensor_stays_unacknowledged(self):
        self.add_sensor(1, axis=float("nan"))
        with self.assertRaisesRegex(ValueError, "sensor axis"):
            self.worker().sync_once()
        self.assertEqual(self.count_outbox(), 0)
        self.assertEqual(self.sent, [])

    def test_unrelated_device_is_not_sent(self):
        with closing(sqlite3.connect(self.source)) as db, db:
            db.execute("INSERT INTO sensor_readings VALUES (?,?,?,?,?,?,?,?,?,?)",
                       (1, "simulator-1", "2026-10-29T08:00:00Z", "2026-10-29T08:00:00Z", 1, 2, 3, 4, 5, 6))
        self.worker().sync_once()
        self.assertEqual(self.sent[0]["readings"], [])

    def test_bounded_outbox_keeps_unscanned_source_for_later(self):
        self.add_sensor(1)
        self.add_sensor(2, "2026-10-29T08:00:01.000Z")
        worker = self.worker()
        with patch("cloud_sync.MAX_OUTBOX", 1):
            self.ok = False
            worker.sync_once()
            self.assertEqual(self.count_outbox(), 1)
            with closing(sqlite3.connect(self.state)) as db:
                self.assertEqual(db.execute("SELECT source_id FROM cursor WHERE kind='sensor'").fetchone()[0], 1)
            self.ok = True
            worker.sync_once()
            worker.sync_once()
        self.assertEqual([item["readings"][0]["source_id"] for item in self.sent], [1, 1, 2])


if __name__ == "__main__":
    unittest.main()
