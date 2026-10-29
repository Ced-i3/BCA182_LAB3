"use client";

import { useEffect, useState } from "react";
import { monitorApi } from "@/lib/api/client";
import type {
  ActivityHistoryResponse, ActivityLatestResponse, HealthResponse,
  ReadingHistoryResponse, SensorReading,
} from "@/lib/api/contracts";

export const REFRESH_INTERVAL_MS = 2000;

export interface MonitorSnapshot {
  health: HealthResponse | null;
  reading: SensorReading | null;
  readings: ReadingHistoryResponse | null;
  activity: ActivityLatestResponse | null;
  history: ActivityHistoryResponse | null;
  fetchedAtMs: number | null;
  errors: { health: boolean; reading: boolean; readings: boolean; activity: boolean; history: boolean };
  cloud?: { state: "live" | "device_offline" | "backend_offline" | "sync_delayed" | "no_data" | "unavailable";
    lastSyncAt: string | null; lastBackendAt: string | null };
}

const initial: MonitorSnapshot = {
  health: null, reading: null, readings: null, activity: null, history: null,
  fetchedAtMs: null,
  errors: { health: false, reading: false, readings: false, activity: false, history: false },
};

function settledValue<T>(result: PromiseSettledResult<T>): T | null {
  return result.status === "fulfilled" ? result.value : null;
}

export function useMonitor(cloudMode = false): { snapshot: MonitorSnapshot; loading: boolean; nowMs: number } {
  const [snapshot, setSnapshot] = useState<MonitorSnapshot>(initial);
  const [loading, setLoading] = useState(true);
  const [nowMs, setNowMs] = useState(() => Date.now());

  useEffect(() => {
    let active = true;
    let timer: ReturnType<typeof setTimeout> | undefined;
    let controller: AbortController | undefined;

    async function poll() {
      controller = new AbortController();
      const signal = controller.signal;
      if (cloudMode) {
        try {
          const response = await fetch("/api/cloud/monitor", { signal });
          if (!response.ok) throw new Error("Cloud unavailable");
          const result = await response.json() as MonitorSnapshot;
          if (active) setSnapshot(result);
        } catch {
          if (active && !signal.aborted) setSnapshot(previous => ({ ...previous,
            health: null, activity: null, fetchedAtMs: Date.now(),
            cloud: { state: "unavailable", lastSyncAt: previous.cloud?.lastSyncAt ?? null,
              lastBackendAt: previous.cloud?.lastBackendAt ?? null },
            errors: { health: true, reading: true, readings: true, activity: true, history: true },
          }));
        }
        if (active) { setLoading(false); timer = setTimeout(poll, 5000); }
        return;
      }
      const [health, reading, readings] = await Promise.allSettled([
        monitorApi.health(signal),
        monitorApi.latestReading(signal),
        monitorApi.readingHistory(signal),
      ]);
      if (!active) return;

      const deviceId = settledValue(reading)?.device_id ?? null;
      const [activity, history] = await Promise.allSettled([
        monitorApi.latestActivity(deviceId, signal),
        monitorApi.activityHistory(deviceId, signal),
      ]);
      if (!active) return;

      setSnapshot({
        health: settledValue(health),
        reading: settledValue(reading),
        readings: settledValue(readings),
        activity: settledValue(activity),
        history: settledValue(history),
        fetchedAtMs: Date.now(),
        errors: {
          health: health.status === "rejected",
          reading: reading.status === "rejected",
          readings: readings.status === "rejected",
          activity: activity.status === "rejected",
          history: history.status === "rejected",
        },
      });
      setLoading(false);
      timer = setTimeout(poll, REFRESH_INTERVAL_MS);
    }

    void poll();
    const clock = setInterval(() => setNowMs(Date.now()), 1000);
    return () => {
      active = false;
      controller?.abort();
      clearTimeout(timer);
      clearInterval(clock);
    };
  }, [cloudMode]);

  return { snapshot, loading, nowMs };
}
