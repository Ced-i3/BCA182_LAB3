import assert from "node:assert/strict";
import test from "node:test";
import {
  parseActivityHistory, parseActivityLatest, parseHealth, parseLatestReading,
  parsePrediction, parseReadingHistory,
} from "./contracts.ts";
import { currentActivity, recentSensorReading } from "../utils/status.ts";

// Controlled fixtures exercise API parsing only; they are not production readings.
const time = "2026-10-18T12:00:00.000Z";
const reading = {
  id: 1, device_id: "test-device", timestamp: time, received_at: time,
  accel_m_s2: { x: 0.1, y: 0.2, z: 9.8 },
  gyro_rad_s: { x: 0.01, y: 0.02, z: 0.03 },
};
const prediction = {
  id: 2, device_id: "test-device", activity_label: "WALKING", activity_code: 1,
  detection_method: "DECISION_TREE", model_version: "test-model",
  window_start_timestamp: time, window_end_timestamp: time, created_at: time,
  experimental: true,
};
const inference = { status: "running", model_loaded: true };
const latest = {
  status: "available", reason: null, device_id_filter: "test-device",
  current_activity: "WALKING", prediction, prediction_age_seconds: 1,
  input_age_seconds: 0.5, is_stale: false, stale_after_seconds: 3,
  experimental: true, inference,
};

test("raw reading and SI axis values parse without conversion", () => {
  assert.deepEqual(parseLatestReading({ reading })?.accel_m_s2, reading.accel_m_s2);
  assert.deepEqual(parseLatestReading({ reading })?.gyro_rad_s, reading.gyro_rad_s);
  assert.equal(parseReadingHistory({ readings: [reading], count: 1 }).count, 1);
  assert.equal(parseLatestReading({ reading: null }), null);
});

test("invalid sensor values and malformed timestamps are rejected", () => {
  assert.throws(() => parseLatestReading({ reading: { ...reading, accel_m_s2: { x: "0.1", y: 0, z: 9 } } }));
  assert.throws(() => parseLatestReading({ reading: { ...reading, timestamp: "2026-10-18T12:00:00" } }));
  assert.throws(() => parseReadingHistory({ readings: [reading], count: 2 }));
});

test("health treats a reachable degraded backend separately from MQTT status", () => {
  const health = parseHealth({ status: "degraded", mqtt_connected: false, activity_inference: inference });
  assert.equal(health.status, "degraded");
  assert.equal(health.mqtt_connected, false);
  assert.equal(parseHealth({ status: "unhealthy", mqtt_connected: false }).activity_inference, null);
});

test("current activity requires a consistent fresh backend result", () => {
  const parsed = parseActivityLatest(latest);
  assert.equal(currentActivity(parsed, 1000, 2000), "WALKING");
  assert.equal(currentActivity(parsed, 1000, 4001), null);
  assert.throws(() => parseActivityLatest({ ...latest, is_stale: true }));
  assert.throws(() => parseActivityLatest({ ...latest, current_activity: "IDLE" }));
});

test("stale, pending and unavailable predictions never become current", () => {
  const stale = parseActivityLatest({ ...latest, status: "unavailable", current_activity: null, is_stale: true });
  const pending = parseActivityLatest({ ...latest, status: "pending", current_activity: null, prediction: null });
  assert.equal(currentActivity(stale, 1000, 1000), null);
  assert.equal(currentActivity(pending, 1000, 1000), null);
  assert.throws(() => parseActivityLatest({ ...latest, status: "pending" }));
});

test("history stays separate from the current prediction", () => {
  const history = parseActivityHistory({ predictions: [prediction], count: 1, limit: 8, device_id_filter: "test-device", experimental: true });
  assert.equal(history.predictions[0].activity_label, "WALKING");
  assert.equal(history.predictions[0].experimental, true);
  assert.throws(() => parsePrediction({ ...prediction, experimental: false }));
  assert.throws(() => parseActivityHistory({ predictions: [prediction], count: 0, limit: 8, device_id_filter: null, experimental: true }));
});

test("empty raw and activity histories are valid empty states", () => {
  assert.deepEqual(parseReadingHistory({ readings: [], count: 0 }).readings, []);
  assert.deepEqual(parseActivityHistory({ predictions: [], count: 0, limit: 8, device_id_filter: null, experimental: true }).predictions, []);
});

test("malformed and disconnected responses cannot become live activity", () => {
  assert.throws(() => parseHealth({ error: "backend unavailable" }));
  assert.throws(() => parseActivityLatest({ ...latest, current_activity: undefined }));
  assert.equal(currentActivity(null, null, Date.now()), null);
});

test("sensor freshness is based on the backend receive time", () => {
  const parsed = parseLatestReading({ reading });
  assert.equal(recentSensorReading(parsed, Date.parse(time) + 4000), true);
  assert.equal(recentSensorReading(parsed, Date.parse(time) + 6000), false);
  assert.equal(recentSensorReading(parsed, 5000, 1, 4000), true);
  assert.equal(recentSensorReading(parsed, 9001, 1, 4000), false);
  assert.equal(recentSensorReading(null, Date.parse(time)), false);
});
