import type { ActivityLabel, ActivityLatestResponse, SensorReading } from "../api/contracts";

export function currentActivity(
  latest: ActivityLatestResponse | null,
  fetchedAtMs: number | null,
  nowMs: number,
): ActivityLabel | null {
  if (!latest || latest.status !== "available" || !latest.prediction ||
      latest.is_stale || latest.prediction_age_seconds === null || fetchedAtMs === null) return null;
  const elapsed = Math.max(0, (nowMs - fetchedAtMs) / 1000);
  return latest.prediction_age_seconds + elapsed <= latest.stale_after_seconds
    ? latest.current_activity : null;
}

export function recentSensorReading(
  reading: SensorReading | null,
  nowMs: number,
  inputAgeSeconds: number | null = null,
  fetchedAtMs: number | null = null,
  staleAfterSeconds = 5,
): boolean {
  if (!reading) return false;
  if (inputAgeSeconds !== null && fetchedAtMs !== null) {
    return inputAgeSeconds + Math.max(0, (nowMs - fetchedAtMs) / 1000) <= staleAfterSeconds;
  }
  const age = nowMs - Date.parse(reading.received_at);
  return age >= -2000 && age <= staleAfterSeconds * 1000;
}

export function localTime(timestamp: string | null | undefined): string {
  if (!timestamp) return "—";
  const date = new Date(timestamp);
  if (!Number.isFinite(date.getTime())) return "—";
  return new Intl.DateTimeFormat(undefined, {
    dateStyle: "medium", timeStyle: "medium",
  }).format(date);
}

export function shortTime(timestamp: string): string {
  const date = new Date(timestamp);
  if (!Number.isFinite(date.getTime())) return "—";
  return new Intl.DateTimeFormat(undefined, { hour: "numeric", minute: "2-digit", second: "2-digit" }).format(date);
}
