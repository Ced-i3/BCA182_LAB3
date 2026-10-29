import assert from "node:assert/strict";
import test from "node:test";
import { cloudSnapshot } from "./snapshot.ts";

const now = Date.parse("2026-10-29T08:00:00Z");
const at = (seconds: number) => new Date(now - seconds * 1000).toISOString();
const sensor = { source_id: 1, device_id: "rt-spark-001", timestamp: at(2), received_at: at(2),
  accel_x: 1, accel_y: 2, accel_z: 3, gyro_x: 4, gyro_y: 5, gyro_z: 6 };
const prediction = { source_id: 1, device_id: "rt-spark-001", activity_label: "WALKING", activity_code: 1,
  detection_method: "DECISION_TREE", model_version: "v1", window_start_timestamp: at(5),
  window_end_timestamp: at(2), created_at: at(2), experimental: true };
const status = { backend_observed_at: at(1), backend_online: true, mqtt_connected: true,
  inference_status: "running", model_loaded: true, last_sensor_received_at: at(2),
  last_successful_sync_at: at(1) };

test("latest and history reuse dashboard contracts", () => {
  const result = cloudSnapshot("rt-spark-001", [sensor], [prediction], status, now);
  assert.equal(result.reading?.accel_m_s2.x, 1);
  assert.equal(result.readings?.count, 1);
  assert.equal(result.activity?.current_activity, "WALKING");
  assert.equal(result.history?.predictions[0].activity_label, "WALKING");
  assert.equal(result.cloud?.state, "live");
});
test("stale, offline, sync delay and empty states never claim current activity", () => {
  for (const [change, expected] of [
    [{ last_sensor_received_at: at(30) }, "device_offline"],
    [{ backend_online: false }, "backend_offline"],
    [{ last_successful_sync_at: at(30) }, "sync_delayed"],
  ] as const) {
    const result = cloudSnapshot("rt-spark-001", [sensor], [prediction], { ...status, ...change }, now);
    assert.equal(result.cloud?.state, expected);
    assert.equal(result.activity?.current_activity, null);
  }
  assert.equal(cloudSnapshot("rt-spark-001", [], [], null, now).cloud?.state, "no_data");
  assert.equal(cloudSnapshot("rt-spark-001", [sensor], [{ ...prediction, created_at: at(30) }], status, now)
    .activity?.current_activity, null);
});
