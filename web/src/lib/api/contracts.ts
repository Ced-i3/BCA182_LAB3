export type ActivityLabel = "IDLE" | "WALKING" | "RUNNING";
export type DetectionMethod = "RULE_BASED" | "DECISION_TREE";

export interface Axes {
  x: number;
  y: number;
  z: number;
}

export interface SensorReading {
  id: number;
  device_id: string;
  timestamp: string;
  received_at: string;
  accel_m_s2: Axes;
  gyro_rad_s: Axes;
}

export interface ActivityPrediction {
  id: number;
  device_id: string;
  activity_label: ActivityLabel;
  activity_code: 0 | 1 | 2;
  detection_method: DetectionMethod;
  model_version: string;
  window_start_timestamp: string;
  window_end_timestamp: string;
  created_at: string;
  experimental: boolean;
}

export interface InferenceHealth {
  status: string;
  model_loaded: boolean;
  queue_depth?: number;
  dropped_samples?: number;
  inference_errors?: number;
}

export interface HealthResponse {
  status: "ok" | "degraded" | "unhealthy";
  mqtt_connected: boolean;
  activity_inference: InferenceHealth | null;
}

export interface ActivityLatestResponse {
  status: "available" | "pending" | "unavailable";
  reason: string | null;
  device_id_filter: string | null;
  current_activity: ActivityLabel | null;
  prediction: ActivityPrediction | null;
  prediction_age_seconds: number | null;
  input_age_seconds: number | null;
  is_stale: boolean;
  stale_after_seconds: number;
  experimental: boolean;
  inference: InferenceHealth;
}

export interface ReadingHistoryResponse {
  readings: SensorReading[];
  count: number;
}

export interface ActivityHistoryResponse {
  predictions: ActivityPrediction[];
  count: number;
  limit: number;
  device_id_filter: string | null;
  experimental: boolean;
}

function record(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function nonempty(value: unknown): value is string {
  return typeof value === "string" && value.length > 0;
}

function number(value: unknown): value is number {
  return typeof value === "number" && Number.isFinite(value);
}

function nonnegative(value: unknown): value is number {
  return number(value) && value >= 0;
}

function integer(value: unknown): value is number {
  return Number.isSafeInteger(value) && typeof value === "number";
}

export function validTimestamp(value: unknown): value is string {
  return typeof value === "string" && /(?:Z|[+-]\d{2}:\d{2})$/.test(value) &&
    Number.isFinite(Date.parse(value));
}

function optionalString(value: unknown): value is string | null {
  return value === null || typeof value === "string";
}

function optionalAge(value: unknown): value is number | null {
  return value === null || nonnegative(value);
}

function axes(value: unknown): value is Axes {
  return record(value) && number(value.x) && number(value.y) && number(value.z);
}

export function parseReading(value: unknown): SensorReading {
  if (!record(value) || !integer(value.id) || !nonempty(value.device_id) ||
      !validTimestamp(value.timestamp) || !validTimestamp(value.received_at) ||
      !axes(value.accel_m_s2) || !axes(value.gyro_rad_s)) {
    throw new Error("Invalid sensor reading from backend.");
  }
  return {
    id: value.id, device_id: value.device_id, timestamp: value.timestamp,
    received_at: value.received_at, accel_m_s2: value.accel_m_s2,
    gyro_rad_s: value.gyro_rad_s,
  };
}

export function parseLatestReading(value: unknown): SensorReading | null {
  if (!record(value) || !("reading" in value)) throw new Error("Invalid latest-reading response.");
  return value.reading === null ? null : parseReading(value.reading);
}

export function parseReadingHistory(value: unknown): ReadingHistoryResponse {
  if (!record(value) || !Array.isArray(value.readings) || !integer(value.count) ||
      value.count !== value.readings.length) throw new Error("Invalid sensor history response.");
  return { readings: value.readings.map(parseReading), count: value.count };
}

const activityCodes: Record<ActivityLabel, number> = { IDLE: 0, WALKING: 1, RUNNING: 2 };

export function parsePrediction(value: unknown): ActivityPrediction {
  if (!record(value) || !integer(value.id) || !nonempty(value.device_id) ||
      !["IDLE", "WALKING", "RUNNING"].includes(String(value.activity_label)) ||
      !integer(value.activity_code) ||
      activityCodes[value.activity_label as ActivityLabel] !== value.activity_code ||
      !["RULE_BASED", "DECISION_TREE"].includes(String(value.detection_method)) ||
      !nonempty(value.model_version) || !validTimestamp(value.window_start_timestamp) ||
      !validTimestamp(value.window_end_timestamp) || !validTimestamp(value.created_at) ||
      value.experimental !== true) throw new Error("Invalid activity prediction from backend.");
  if ((value.activity_label === "IDLE") !== (value.detection_method === "RULE_BASED")) {
    throw new Error("Invalid activity detection method from backend.");
  }
  return {
    id: value.id, device_id: value.device_id,
    activity_label: value.activity_label as ActivityLabel,
    activity_code: value.activity_code as 0 | 1 | 2,
    detection_method: value.detection_method as DetectionMethod,
    model_version: value.model_version,
    window_start_timestamp: value.window_start_timestamp,
    window_end_timestamp: value.window_end_timestamp,
    created_at: value.created_at,
    experimental: true,
  };
}

function parseInference(value: unknown): InferenceHealth {
  if (!record(value) || !nonempty(value.status) || typeof value.model_loaded !== "boolean") {
    throw new Error("Invalid inference status from backend.");
  }
  return {
    status: value.status,
    model_loaded: value.model_loaded,
    queue_depth: nonnegative(value.queue_depth) ? value.queue_depth : undefined,
    dropped_samples: nonnegative(value.dropped_samples) ? value.dropped_samples : undefined,
    inference_errors: nonnegative(value.inference_errors) ? value.inference_errors : undefined,
  };
}

export function parseHealth(value: unknown): HealthResponse {
  if (!record(value) || !["ok", "degraded", "unhealthy"].includes(String(value.status)) ||
      typeof value.mqtt_connected !== "boolean") throw new Error("Invalid health response.");
  return {
    status: value.status as HealthResponse["status"],
    mqtt_connected: value.mqtt_connected,
    activity_inference: value.activity_inference === undefined
      ? null : parseInference(value.activity_inference),
  };
}

export function parseActivityLatest(value: unknown): ActivityLatestResponse {
  if (!record(value) || !["available", "pending", "unavailable"].includes(String(value.status)) ||
      !optionalString(value.reason) || !optionalString(value.device_id_filter) ||
      !(value.current_activity === null ||
        ["IDLE", "WALKING", "RUNNING"].includes(String(value.current_activity))) ||
      !optionalAge(value.prediction_age_seconds) || !optionalAge(value.input_age_seconds) ||
      typeof value.is_stale !== "boolean" || !number(value.stale_after_seconds) ||
      value.stale_after_seconds <= 0 || value.experimental !== true) {
    throw new Error("Invalid latest-activity response.");
  }
  const prediction = value.prediction === null ? null : parsePrediction(value.prediction);
  const inference = parseInference(value.inference);
  if (value.status === "available") {
    if (!prediction || value.current_activity !== prediction.activity_label ||
        value.is_stale || value.prediction_age_seconds === null) {
      throw new Error("Inconsistent current activity from backend.");
    }
  } else if (value.current_activity !== null) {
    throw new Error("Unavailable activity must not be shown as current.");
  }
  return {
    status: value.status as ActivityLatestResponse["status"],
    reason: value.reason,
    device_id_filter: value.device_id_filter,
    current_activity: value.current_activity as ActivityLabel | null,
    prediction,
    prediction_age_seconds: value.prediction_age_seconds,
    input_age_seconds: value.input_age_seconds,
    is_stale: value.is_stale,
    stale_after_seconds: value.stale_after_seconds,
    experimental: true,
    inference,
  };
}

export function parseActivityHistory(value: unknown): ActivityHistoryResponse {
  if (!record(value) || !Array.isArray(value.predictions) || !integer(value.count) ||
      value.count !== value.predictions.length || !integer(value.limit) ||
      !optionalString(value.device_id_filter) || value.experimental !== true) {
    throw new Error("Invalid activity history response.");
  }
  return {
    predictions: value.predictions.map(parsePrediction),
    count: value.count,
    limit: value.limit,
    device_id_filter: value.device_id_filter,
    experimental: true,
  };
}
