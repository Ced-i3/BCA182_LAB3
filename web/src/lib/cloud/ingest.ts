import { createHash, timingSafeEqual } from "node:crypto";
import { validTimestamp } from "../api/contracts.ts";

type ObjectValue = Record<string, unknown>;
const labels = { IDLE: 0, WALKING: 1, RUNNING: 2 } as const;

function object(value: unknown): value is ObjectValue {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}
function exact(value: ObjectValue, keys: string[]): boolean {
  return Object.keys(value).sort().join("|") === keys.sort().join("|");
}
function id(value: unknown): value is number {
  return typeof value === "number" && Number.isSafeInteger(value) && value > 0;
}
function sourceTime(value: unknown): value is string {
  return validTimestamp(value) && Date.parse(value) >= Date.UTC(2000, 0, 1) &&
    Date.parse(value) <= Date.now() + 300_000;
}
function axes(value: unknown): value is { x: number; y: number; z: number } {
  return object(value) && exact(value, ["x", "y", "z"]) &&
    [value.x, value.y, value.z].every(x => typeof x === "number" && Number.isFinite(x) && Math.abs(x) <= 1000);
}
function reading(value: unknown): boolean {
  if (!object(value) || !exact(value, ["event_id", "source_id", "timestamp", "received_at", "accel_m_s2", "gyro_rad_s"])) return false;
  return id(value.source_id) && value.event_id === `sensor:${value.source_id}` &&
    sourceTime(value.timestamp) && sourceTime(value.received_at) && axes(value.accel_m_s2) && axes(value.gyro_rad_s);
}
function prediction(value: unknown): boolean {
  if (!object(value) || !exact(value, ["event_id", "source_id", "activity_label", "activity_code", "detection_method", "model_version", "window_start_timestamp", "window_end_timestamp", "created_at", "experimental"])) return false;
  const label = value.activity_label;
  return id(value.source_id) && value.event_id === `prediction:${value.source_id}` &&
    typeof label === "string" && label in labels &&
    value.activity_code === labels[label as keyof typeof labels] &&
    value.detection_method === (label === "IDLE" ? "RULE_BASED" : "DECISION_TREE") &&
    typeof value.model_version === "string" && value.model_version.length > 0 && value.model_version.length <= 120 &&
    sourceTime(value.window_start_timestamp) && sourceTime(value.window_end_timestamp) &&
    sourceTime(value.created_at) && value.experimental === true &&
    Date.parse(value.window_start_timestamp) <= Date.parse(value.window_end_timestamp);
}
export interface IngestBody {
  device_id: string;
  readings: Array<ObjectValue>;
  predictions: Array<ObjectValue>;
  status: {
    backend_observed_at: string; backend_online: boolean; mqtt_connected: boolean; inference_status: string;
    model_loaded: boolean; last_sensor_received_at: string | null;
  };
}
export function parseIngest(value: unknown): IngestBody {
  if (!object(value) || !exact(value, ["device_id", "readings", "predictions", "status"]) ||
      typeof value.device_id !== "string" || !/^[A-Za-z0-9](?:[A-Za-z0-9._-]{0,30}[A-Za-z0-9])?$/.test(value.device_id) ||
      !Array.isArray(value.readings) || !Array.isArray(value.predictions) ||
      value.readings.length + value.predictions.length > 25 ||
      !value.readings.every(reading) || !value.predictions.every(prediction) || !object(value.status) ||
      !exact(value.status, ["backend_observed_at", "backend_online", "mqtt_connected", "inference_status", "model_loaded", "last_sensor_received_at"]) ||
      !sourceTime(value.status.backend_observed_at) || typeof value.status.backend_online !== "boolean" ||
      typeof value.status.mqtt_connected !== "boolean" ||
      typeof value.status.model_loaded !== "boolean" ||
      typeof value.status.inference_status !== "string" || value.status.inference_status.length > 40 ||
      !(value.status.last_sensor_received_at === null || sourceTime(value.status.last_sensor_received_at))) {
    throw new Error("Invalid ingest payload");
  }
  return value as unknown as IngestBody;
}

export function matchingDevice(token: string, configured: string | undefined): string | null {
  if (token.length < 32 || token.length > 256 || !configured) return null;
  let entries: unknown;
  try { entries = JSON.parse(configured); } catch { return null; }
  if (!object(entries)) return null;
  const actual = createHash("sha256").update(token).digest();
  let match: string | null = null;
  for (const [device, digest] of Object.entries(entries)) {
    if (typeof digest !== "string" || !/^[a-f0-9]{64}$/.test(digest)) continue;
    const expected = Buffer.from(digest, "hex");
    if (timingSafeEqual(actual, expected)) match = device;
  }
  return match;
}

export interface IngestStore {
  owner(deviceId: string): Promise<string | null>;
  readings(rows: ObjectValue[]): Promise<void>;
  predictions(rows: ObjectValue[]): Promise<void>;
  status(row: ObjectValue): Promise<void>;
}

export async function ingest(request: Request, store: IngestStore,
                             tokenMap: string | undefined): Promise<Response> {
  const headers = { "Cache-Control": "no-store", "X-Content-Type-Options": "nosniff" };
  const reply = (status: number, error: string) => Response.json({ error }, { status, headers });
  if (process.env.NODE_ENV === "production" && new URL(request.url).protocol !== "https:")
    return reply(400, "HTTPS required.");
  const authorization = request.headers.get("authorization") ?? "";
  if (!/^Bearer [A-Za-z0-9_-]{32,256}$/.test(authorization)) return reply(401, "Unauthorized.");
  const deviceId = matchingDevice(authorization.slice(7), tokenMap);
  if (!deviceId) return reply(401, "Unauthorized.");
  if (!request.headers.get("content-type")?.toLowerCase().startsWith("application/json")) return reply(415, "JSON required.");
  const declared = Number(request.headers.get("content-length") ?? "0");
  if (declared > 64 * 1024) return reply(413, "Request too large.");
  let raw: string;
  try {
    const stream = request.body;
    if (!stream) return reply(400, "Invalid request body.");
    const reader = stream.getReader();
    const chunks: Uint8Array[] = [];
    let size = 0;
    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      size += value.byteLength;
      if (size > 64 * 1024) {
        await reader.cancel();
        return reply(413, "Request too large.");
      }
      chunks.push(value);
    }
    const bytes = new Uint8Array(size);
    let offset = 0;
    for (const chunk of chunks) { bytes.set(chunk, offset); offset += chunk.byteLength; }
    raw = new TextDecoder("utf-8", { fatal: true }).decode(bytes);
  } catch { return reply(400, "Invalid request body."); }
  let body: IngestBody;
  try { body = parseIngest(JSON.parse(raw)); }
  catch { return reply(400, "Invalid ingest payload."); }
  if (body.device_id !== deviceId) return reply(403, "Device not authorized.");
  try {
    const owner = await store.owner(deviceId);
    if (!owner) return reply(403, "Device not registered.");
    const common = { device_id: deviceId, owner_id: owner };
    await store.readings(body.readings.map(row => ({
      ...common, event_id: row.event_id, source_id: row.source_id,
      timestamp: row.timestamp, received_at: row.received_at,
      accel_x: (row.accel_m_s2 as ObjectValue).x,
      accel_y: (row.accel_m_s2 as ObjectValue).y,
      accel_z: (row.accel_m_s2 as ObjectValue).z,
      gyro_x: (row.gyro_rad_s as ObjectValue).x,
      gyro_y: (row.gyro_rad_s as ObjectValue).y,
      gyro_z: (row.gyro_rad_s as ObjectValue).z,
    })));
    await store.predictions(body.predictions.map(row => ({ ...common, ...row })));
    await store.status({ ...common, ...body.status, last_successful_sync_at: new Date().toISOString() });
    return Response.json({ accepted: true }, { status: 200, headers });
  } catch {
    return reply(503, "Cloud storage unavailable; retry later.");
  }
}
