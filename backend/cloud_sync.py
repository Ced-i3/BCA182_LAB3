"""Outbound-only, durable mirror of one device from local SQLite to cloud.

Run as a separate process. The source database is opened read-only. A bounded
outbox and scan cursor live in a different SQLite file; source rows are never
acknowledged before the ingest endpoint confirms the whole batch.
"""

from __future__ import annotations

import json
import logging
import math
import os
import sqlite3
import time
import urllib.error
import urllib.request
from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

LOGGER = logging.getLogger("lab3.cloud_sync")
ROOT = Path(__file__).resolve().parent
MAX_OUTBOX = 10000
MAX_BATCH = 25


def utc(value: str) -> str:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError("timestamp must include a timezone")
    return parsed.astimezone(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def axes(row: sqlite3.Row, prefix: str, maximum: float = 1000) -> dict[str, float]:
    try:
        result = {axis: float(row[f"{prefix}_{axis}"]) for axis in "xyz"}
    except (TypeError, ValueError) as error:
        raise ValueError("sensor axis outside cloud bounds") from error
    if not all(math.isfinite(value) and abs(value) <= maximum for value in result.values()):
        raise ValueError("sensor axis outside cloud bounds")
    return result


class CloudSync:
    def __init__(self, source: Path, state: Path, device_id: str, token: str,
                 endpoint: str, *, batch_size: int = 25, interval: float = 5,
                 include_existing: bool = False,
                 sender: Callable[[str, str, dict[str, Any]], bool] | None = None,
                 health: Callable[[], dict[str, Any]] | None = None) -> None:
        if not device_id or not token or len(token) < 32 or not endpoint.startswith("https://"):
            raise ValueError("device, strong token, and HTTPS ingest URL are required")
        if not 1 <= batch_size <= MAX_BATCH or not 1 <= interval <= 300:
            raise ValueError("batch size or interval outside supported range")
        self.source, self.state, self.device_id = source, state, device_id
        self.token, self.endpoint, self.batch_size, self.interval = token, endpoint, batch_size, interval
        self.sender = sender or send_https
        self.health = health or local_health
        self._last_send_ok = False
        state.parent.mkdir(parents=True, exist_ok=True)
        with closing(sqlite3.connect(state)) as db, db:
            db.executescript("""
                CREATE TABLE IF NOT EXISTS cursor (
                    kind TEXT PRIMARY KEY, source_id INTEGER NOT NULL,
                    last_second TEXT
                );
                CREATE TABLE IF NOT EXISTS outbox (
                    kind TEXT NOT NULL, source_id INTEGER NOT NULL,
                    payload TEXT NOT NULL, PRIMARY KEY(kind, source_id)
                );
            """)
            if not include_existing:
                # Establish the first-run fence before polling. Existing source
                # rows require separate approval for a historical backfill.
                with closing(self._source()) as source:
                    for kind, table in (("sensor", "sensor_readings"),
                                        ("prediction", "activity_predictions")):
                        columns = "id, received_at" if kind == "sensor" else "id, NULL"
                        row = source.execute(
                            f"SELECT {columns} FROM {table} WHERE device_id=? ORDER BY id DESC LIMIT 1",
                            (device_id,),
                        ).fetchone()
                        last_id = row[0] if row else 0
                        last_second = utc(row[1])[:19] if row and row[1] else None
                        db.execute("INSERT OR IGNORE INTO cursor VALUES (?,?,?)",
                                   (kind, last_id, last_second))

    def _source(self) -> sqlite3.Connection:
        # URI mode=ro prevents accidental edits to historical records.
        db = sqlite3.connect(self.source.resolve().as_uri() + "?mode=ro", uri=True)
        db.row_factory = sqlite3.Row
        return db

    def stage(self) -> int:
        """Stage selected rows transactionally; stop scanning at the outbox cap."""
        staged = 0
        with closing(self._source()) as source, closing(sqlite3.connect(self.state)) as state, state:
            state.execute("BEGIN IMMEDIATE")
            remaining = MAX_OUTBOX - state.execute("SELECT count(*) FROM outbox").fetchone()[0]
            if remaining <= 0:
                return 0
            for kind, table in (("sensor", "sensor_readings"), ("prediction", "activity_predictions")):
                cursor = state.execute("SELECT source_id, last_second FROM cursor WHERE kind=?", (kind,)).fetchone()
                last_id, last_second = cursor if cursor else (0, None)
                rows = source.execute(
                    f"SELECT * FROM {table} WHERE device_id=? AND id>? ORDER BY id LIMIT ?",
                    (self.device_id, last_id, min(1000, remaining + 100)),
                )
                for row in rows:
                    if kind == "sensor":
                        second = utc(row["received_at"])[:19]
                        selected = second != last_second
                        if selected:
                            payload = {
                                "event_id": f"sensor:{row['id']}", "source_id": row["id"],
                                "timestamp": utc(row["timestamp"]), "received_at": utc(row["received_at"]),
                                "accel_m_s2": axes(row, "accel"), "gyro_rad_s": axes(row, "gyro"),
                            }
                    else:
                        selected = True
                        second = last_second
                        label = row["activity_label"]
                        code = {"IDLE": 0, "WALKING": 1, "RUNNING": 2}.get(label)
                        if code is None or code != row["activity_code"] or row["experimental"] != 1:
                            raise ValueError("invalid source prediction")
                        payload = {
                            "event_id": f"prediction:{row['id']}", "source_id": row["id"],
                            "activity_label": label, "activity_code": code,
                            "detection_method": row["detection_method"],
                            "model_version": row["model_version"],
                            "window_start_timestamp": utc(row["window_start_timestamp"]),
                            "window_end_timestamp": utc(row["window_end_timestamp"]),
                            "created_at": utc(row["created_at"]), "experimental": True,
                        }
                    if selected:
                        if remaining <= 0:
                            break
                        state.execute("INSERT OR IGNORE INTO outbox VALUES (?,?,?)",
                                      (kind, row["id"], json.dumps(payload, separators=(",", ":"))))
                        remaining -= 1
                        staged += 1
                        last_second = second
                    last_id = row["id"]
                state.execute("INSERT INTO cursor VALUES (?,?,?) ON CONFLICT(kind) DO UPDATE SET "
                              "source_id=excluded.source_id, last_second=excluded.last_second",
                              (kind, last_id, last_second))
        return staged

    def sync_once(self) -> int:
        self._last_send_ok = False
        self.stage()
        with closing(sqlite3.connect(self.state)) as state:
            rows = state.execute("SELECT kind, source_id, payload FROM outbox "
                                 "ORDER BY kind, source_id LIMIT ?", (self.batch_size,)).fetchall()
        with closing(self._source()) as source:
            latest = source.execute("SELECT received_at FROM sensor_readings WHERE device_id=? "
                                    "ORDER BY id DESC LIMIT 1", (self.device_id,)).fetchone()
        try:
            health = self.health()
            backend_online = True
        except (OSError, urllib.error.URLError, TimeoutError, ValueError):
            health = {}
            backend_online = False
        inference = health.get("activity_inference") or {}
        status = {
            "backend_observed_at": datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z"),
            "backend_online": backend_online,
            "mqtt_connected": health.get("mqtt_connected") is True,
            "inference_status": str(inference.get("status", "unavailable"))[:40],
            "model_loaded": inference.get("model_loaded") is True,
            "last_sensor_received_at": utc(latest[0]) if latest else None,
        }
        body = {"device_id": self.device_id,
                "readings": [json.loads(row[2]) for row in rows if row[0] == "sensor"],
                "predictions": [json.loads(row[2]) for row in rows if row[0] == "prediction"],
                "status": status}
        try:
            accepted = self.sender(self.endpoint, self.token, body)
        except (OSError, urllib.error.URLError, TimeoutError, ValueError):
            accepted = False
        if not accepted:
            return 0
        self._last_send_ok = True
        with closing(sqlite3.connect(self.state)) as state, state:
            state.executemany("DELETE FROM outbox WHERE kind=? AND source_id=?",
                              [(kind, source_id) for kind, source_id, _ in rows])
        return len(rows)

    def run(self) -> None:
        failures = 0
        while True:
            try:
                self.sync_once()
                failures = 0 if self._last_send_ok else min(failures + 1, 6)
            except (sqlite3.Error, ValueError) as error:
                LOGGER.error("Sync source/state error: %s", error)
                failures = min(failures + 1, 6)
            time.sleep(min(300, self.interval * (2 ** failures)))


def send_https(endpoint: str, token: str, body: dict[str, Any]) -> bool:
    data = json.dumps(body, separators=(",", ":")).encode()
    if len(data) > 64 * 1024:
        raise ValueError("batch exceeds ingest request limit")
    request = urllib.request.Request(endpoint, data=data, method="POST", headers={
        "Authorization": f"Bearer {token}", "Content-Type": "application/json",
        "Accept": "application/json",
    })
    try:
        with urllib.request.urlopen(request, timeout=10) as response:
            return response.status == 200 and json.load(response).get("accepted") is True
    except urllib.error.HTTPError as error:
        LOGGER.warning("Cloud ingest returned HTTP %s", error.code)
        return False


def local_health() -> dict[str, Any]:
    try:
        with urllib.request.urlopen("http://127.0.0.1:5000/health", timeout=3) as response:
            return json.load(response)
    except urllib.error.HTTPError as error:
        if error.code == 503:
            return json.load(error)
        raise


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    token = os.environ.get("CLOUD_INGEST_TOKEN", "")
    worker = CloudSync(
        Path(os.environ.get("MOTION_DB_PATH", ROOT / "data" / "motion.db")),
        Path(os.environ.get("CLOUD_SYNC_STATE_PATH", ROOT / "data" / "cloud_sync.db")),
        os.environ.get("CLOUD_DEVICE_ID", ""), token,
        os.environ.get("CLOUD_INGEST_URL", ""),
        batch_size=int(os.environ.get("CLOUD_SYNC_BATCH_SIZE", "25")),
        interval=float(os.environ.get("CLOUD_SYNC_INTERVAL_SECONDS", "5")),
    )
    worker.run()


if __name__ == "__main__":
    main()
