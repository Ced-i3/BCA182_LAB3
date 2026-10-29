import assert from "node:assert/strict";
import test from "node:test";
import { serveCloudMonitor, type CloudReader } from "./monitor.ts";

function reader(owner: string | null, device: string | null): CloudReader & { calls: string[] } {
  return { calls: [],
    async claims() { this.calls.push("claims"); return owner; },
    async firstDevice(identity) { this.calls.push(`device:${identity}`); return device; },
    async sensors(identity, id) { this.calls.push(`sensors:${identity}:${id}`); return []; },
    async predictions(identity, id) { this.calls.push(`predictions:${identity}:${id}`); return []; },
    async status(identity, id) { this.calls.push(`status:${identity}:${id}`); return null; },
  };
}
test("signed-out request does not read private tables", async () => {
  const source = reader(null, "rt-spark-001");
  assert.equal((await serveCloudMonitor(source)).status, 401);
  assert.deepEqual(source.calls, ["claims"]);
});
test("user without an owned registered device cannot read other devices", async () => {
  const source = reader("other-owner", null);
  assert.equal((await serveCloudMonitor(source)).status, 403);
  assert.deepEqual(source.calls, ["claims", "device:other-owner"]);
});
test("owner and device are passed to every read; cloud failure is controlled", async () => {
  const source = reader("owner-1", "rt-spark-001");
  const response = await serveCloudMonitor(source);
  assert.equal(response.status, 200);
  assert.equal(response.headers.get("cache-control"), "private, no-store");
  assert.deepEqual(source.calls.slice(2).sort(), [
    "predictions:owner-1:rt-spark-001", "sensors:owner-1:rt-spark-001", "status:owner-1:rt-spark-001",
  ]);
  source.sensors = async () => { throw new Error("private database exception"); };
  const failure = await serveCloudMonitor(source);
  assert.equal(failure.status, 503);
  assert.equal(JSON.stringify(await failure.json()).includes("private database exception"), false);
});
