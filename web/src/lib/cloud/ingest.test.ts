import assert from "node:assert/strict";
import { createHash } from "node:crypto";
import test from "node:test";
import { ingest, type IngestStore } from "./ingest.ts";

const token = "a".repeat(40);
const hashes = JSON.stringify({ "rt-spark-001": createHash("sha256").update(token).digest("hex") });
const time = new Date().toISOString();
const reading = { event_id: "sensor:1", source_id: 1, timestamp: time, received_at: time,
  accel_m_s2: { x: 1, y: 2, z: 3 }, gyro_rad_s: { x: 4, y: 5, z: 6 } };
const prediction = { event_id: "prediction:1", source_id: 1, activity_label: "WALKING", activity_code: 1,
  detection_method: "DECISION_TREE", model_version: "v1", window_start_timestamp: time,
  window_end_timestamp: time, created_at: time, experimental: true };
const status = { backend_observed_at: time, backend_online: true, mqtt_connected: true,
  inference_status: "running", model_loaded: true, last_sensor_received_at: time };
function body(extra: object = {}) { return { device_id: "rt-spark-001", readings: [reading], predictions: [prediction], status, ...extra }; }
function request(payload: unknown, bearer: string | null = token, headers: Record<string, string> = {}) {
  return new Request("https://example.test/api/cloud/ingest", { method: "POST", headers: {
    "content-type": "application/json", ...(bearer ? { authorization: `Bearer ${bearer}` } : {}), ...headers,
  }, body: typeof payload === "string" ? payload : JSON.stringify(payload) });
}
function fakeStore(): IngestStore & { seen: Set<string>; writes: number; fail: boolean; registered: boolean } {
  return { seen: new Set(), writes: 0, fail: false, registered: true,
    async owner() { return this.registered ? "owner-uuid" : null; },
    async readings(rows) { if (this.fail) throw new Error("db down");
      for (const row of rows) { this.seen.add(String(row.event_id)); this.writes++; } },
    async predictions(rows) { for (const row of rows) this.seen.add(String(row.event_id)); },
    async status() {},
  };
}

test("ingest rejects missing and invalid credentials before storage", async () => {
  const store = fakeStore();
  assert.equal((await ingest(request(body(), null), store, hashes)).status, 401);
  assert.equal((await ingest(request(body(), "b".repeat(40)), store, hashes)).status, 401);
  assert.equal(store.writes, 0);
});
test("ingest rejects oversized and malformed bodies", async () => {
  const store = fakeStore();
  assert.equal((await ingest(request(body(), token, { "content-length": "65537" }), store, hashes)).status, 413);
  assert.equal((await ingest(request("x".repeat(70_000), token), store, hashes)).status, 413);
  assert.equal((await ingest(request("{oops", token), store, hashes)).status, 400);
  assert.equal((await ingest(request(body({ readings: [{ ...reading, accel_m_s2: { x: 1e100, y: 2, z: 3 } }] })), store, hashes)).status, 400);
});
test("ingest binds token to registered device and owner", async () => {
  const store = fakeStore();
  assert.equal((await ingest(request(body({ device_id: "other-device" })), store, hashes)).status, 403);
  store.registered = false;
  assert.equal((await ingest(request(body(), token), store, hashes)).status, 403);
  assert.equal(store.writes, 0);
});
test("valid ingest writes reading, prediction, status and can retry stable event IDs", async () => {
  const store = fakeStore();
  assert.equal((await ingest(request(body()), store, hashes)).status, 200);
  assert.deepEqual([...store.seen].sort(), ["prediction:1", "sensor:1"]);
  assert.equal((await ingest(request(body()), store, hashes)).status, 200);
  assert.equal(store.seen.size, 2);
});
test("database failure is retryable without leaking payload", async () => {
  const store = fakeStore(); store.fail = true;
  const response = await ingest(request(body()), store, hashes);
  assert.equal(response.status, 503);
  assert.equal(JSON.stringify(await response.json()).includes("accel"), false);
});
