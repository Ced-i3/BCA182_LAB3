import {
  parseActivityHistory, parseActivityLatest, parseHealth, parseLatestReading,
  parseReadingHistory,
  type ActivityHistoryResponse, type ActivityLatestResponse, type HealthResponse,
  type ReadingHistoryResponse, type SensorReading,
} from "./contracts";

async function get<T>(path: string, parse: (value: unknown) => T, signal: AbortSignal): Promise<T> {
  const response = await fetch(`/api/monitor/${path}`, {
    cache: "no-store",
    signal,
    headers: { Accept: "application/json" },
  });
  const body: unknown = await response.json();
  // Flask returns 503 for a reachable but degraded /health response.
  if (!response.ok && !(path === "health" && response.status === 503 &&
      typeof body === "object" && body !== null && "status" in body)) {
    throw new Error("Monitoring server is unavailable.");
  }
  return parse(body);
}

export const monitorApi = {
  health: (signal: AbortSignal): Promise<HealthResponse> =>
    get("health", parseHealth, signal),
  latestReading: (signal: AbortSignal): Promise<SensorReading | null> =>
    get("latest", parseLatestReading, signal),
  readingHistory: (signal: AbortSignal): Promise<ReadingHistoryResponse> =>
    get("history?limit=10", parseReadingHistory, signal),
  latestActivity: (deviceId: string | null, signal: AbortSignal): Promise<ActivityLatestResponse> =>
    get(`activity/latest${deviceId ? `?device_id=${encodeURIComponent(deviceId)}` : ""}`,
      parseActivityLatest, signal),
  activityHistory: (deviceId: string | null, signal: AbortSignal): Promise<ActivityHistoryResponse> =>
    get(`activity/history?limit=8${deviceId ? `&device_id=${encodeURIComponent(deviceId)}` : ""}`,
      parseActivityHistory, signal),
};
