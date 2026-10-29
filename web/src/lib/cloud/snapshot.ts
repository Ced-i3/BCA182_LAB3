import { parsePrediction, parseReading, type ActivityLatestResponse, type HealthResponse } from "../api/contracts.ts";
import type { MonitorSnapshot } from "../../hooks/use-monitor";

export type CloudState = "live" | "device_offline" | "backend_offline" | "sync_delayed" | "no_data";
type Row = Record<string, unknown>;
function reading(row: Row) {
  return parseReading({ id: row.source_id, device_id: row.device_id, timestamp: row.timestamp,
    received_at: row.received_at, accel_m_s2: { x: row.accel_x, y: row.accel_y, z: row.accel_z },
    gyro_rad_s: { x: row.gyro_x, y: row.gyro_y, z: row.gyro_z } });
}
function prediction(row: Row) { return parsePrediction({ ...row, id: row.source_id }); }
function age(value: string | null, now: number): number | null {
  return value ? Math.max(0, (now - Date.parse(value)) / 1000) : null;
}
export function cloudSnapshot(deviceId: string, sensorRows: Row[], predictionRows: Row[],
                              status: Row | null, now = Date.now()): MonitorSnapshot {
  const readings = sensorRows.map(reading);
  const predictions = predictionRows.map(prediction);
  const newest = readings[0] ?? null;
  const latest = predictions[0] ?? null;
  const syncTime = typeof status?.last_successful_sync_at === "string" ? status.last_successful_sync_at : null;
  const backendTime = typeof status?.backend_observed_at === "string" ? status.backend_observed_at : null;
  const lastSensor = typeof status?.last_sensor_received_at === "string" ? status.last_sensor_received_at : null;
  const backendAge = age(backendTime, now), syncAge = age(syncTime, now), sensorAge = age(lastSensor, now);
  const predictionAge = latest ? Math.max(age(latest.created_at, now) ?? Infinity,
    age(latest.window_end_timestamp, now) ?? Infinity) : null;
  const synced = syncAge !== null && syncAge <= 20;
  const backendFresh = backendAge !== null && backendAge <= 20;
  const deviceFresh = sensorAge !== null && sensorAge <= 15 && status?.mqtt_connected === true;
  const state: CloudState = !newest && !lastSensor ? "no_data" : !synced ? "sync_delayed" :
    !backendFresh || status?.backend_online !== true ? "backend_offline" : !deviceFresh ? "device_offline" : "live";
  const inference = { status: status?.inference_status === "running" ? "running" : "unavailable",
    model_loaded: status?.model_loaded === true };
  const health: HealthResponse = { status: state === "live" ? "ok" : "degraded",
    mqtt_connected: status?.mqtt_connected === true && backendFresh && synced, activity_inference: inference };
  const current = state === "live" && predictionAge !== null && predictionAge <= 15 &&
    inference.status === "running" && inference.model_loaded;
  const activity: ActivityLatestResponse = {
    status: current ? "available" : state === "live" && inference.status === "running" ? "pending" : "unavailable",
    reason: current ? null : state, device_id_filter: deviceId,
    current_activity: current ? latest!.activity_label : null, prediction: latest,
    prediction_age_seconds: predictionAge, input_age_seconds: sensorAge,
    is_stale: latest !== null && !current, stale_after_seconds: 15, experimental: true, inference,
  };
  return { health, reading: newest, readings: { readings, count: readings.length },
    activity, history: { predictions, count: predictions.length, limit: 8,
      device_id_filter: deviceId, experimental: true }, fetchedAtMs: now,
    errors: { health: false, reading: false, readings: false, activity: false, history: false },
    cloud: { state, lastSyncAt: syncTime, lastBackendAt: backendTime } };
}
