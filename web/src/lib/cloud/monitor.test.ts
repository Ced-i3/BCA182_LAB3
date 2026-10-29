import assert from "node:assert/strict";
import test from "node:test";
import { PUBLIC_DEVICE_ID, serveCloudMonitor, type PublicCloudReader } from "./monitor.ts";

const request = (query = "") => new Request(`https://demo.example/api/cloud/monitor${query}`);
function reader(registered = true): PublicCloudReader & { calls: string[] } {
  return { calls: [],
    async registered(device) { this.calls.push(`registered:${device}`); return registered; },
    async sensors(device) { this.calls.push(`sensors:${device}`); return []; },
    async predictions(device) { this.calls.push(`predictions:${device}`); return []; },
    async status(device) { this.calls.push(`status:${device}`); return null; },
  };
}

test("anonymous public read is fixed to the registered demo device", async () => {
  const source = reader();
  const response = await serveCloudMonitor(source, request());
  assert.equal(response.status, 200);
  assert.match(response.headers.get("cache-control") ?? "", /s-maxage=3/);
  assert.deepEqual(source.calls, ["registered:rt-spark-001", "sensors:rt-spark-001",
    "predictions:rt-spark-001", "status:rt-spark-001"]);
  const body = await response.json();
  assert.equal(body.cloud.state, "no_data");
  assert.equal(body.activity.device_id_filter, PUBLIC_DEVICE_ID);
  assert.equal(JSON.stringify(body).includes("owner_id"), false);
});

test("query parameters cannot select another device or bypass the cache", async () => {
  const source = reader();
  const response = await serveCloudMonitor(source, request("?device_id=other&owner_id=secret"));
  assert.equal(response.status, 400);
  assert.deepEqual(source.calls, []);
  assert.equal(response.headers.get("cache-control"), "no-store");
});

test("disabled or missing device cannot be read", async () => {
  const source = reader(false);
  assert.equal((await serveCloudMonitor(source, request())).status, 503);
  assert.deepEqual(source.calls, ["registered:rt-spark-001"]);
});

test("public snapshot strips private fields and foreign-device rows", async () => {
  const source = reader();
  const stamp = new Date().toISOString();
  const reading = { source_id: 7, device_id: PUBLIC_DEVICE_ID, timestamp: stamp,
    received_at: stamp, accel_x: 1, accel_y: 2, accel_z: 3,
    gyro_x: 4, gyro_y: 5, gyro_z: 6, owner_id: "private-owner", secret: "private-token" };
  source.sensors = async () => [{ ...reading, device_id: "other-device" }, reading];
  const response = await serveCloudMonitor(source, request());
  const body = await response.json();
  assert.equal(body.readings.count, 1);
  assert.equal(body.reading.accel_m_s2.x, 1);
  assert.equal(body.reading.device_id, PUBLIC_DEVICE_ID);
  assert.equal(JSON.stringify(body).includes("private-owner"), false);
  assert.equal(JSON.stringify(body).includes("private-token"), false);
  assert.equal(JSON.stringify(body).includes("other-device"), false);
});

test("cloud failures are controlled and never disclose database exceptions", async () => {
  const source = reader();
  source.sensors = async () => { throw new Error("private database exception"); };
  const response = await serveCloudMonitor(source, request());
  assert.equal(response.status, 503);
  assert.equal(response.headers.get("cache-control"), "no-store");
  assert.equal(JSON.stringify(await response.json()).includes("private database exception"), false);
});
