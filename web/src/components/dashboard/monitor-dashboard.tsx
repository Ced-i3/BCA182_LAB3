"use client";

import { ActivityPanel } from "./activity-panel";
import { SensorPanel } from "./sensor-panel";
import { HistoryPanel } from "./history-panel";
import { SystemPanel } from "./system-panel";
import { useMonitor } from "@/hooks/use-monitor";
import { currentActivity, recentSensorReading } from "@/lib/utils/status";

export function MonitorDashboard({ cloudMode = false }: { cloudMode?: boolean }) {
  const { snapshot, loading, nowMs } = useMonitor(cloudMode);
  const backendOnline = snapshot.health !== null && (!cloudMode || snapshot.cloud?.state !== "unavailable");
  const backendUnhealthy = snapshot.health?.status === "unhealthy";
  const activity = currentActivity(snapshot.activity, snapshot.fetchedAtMs, nowMs);
  const sensorFresh = (!cloudMode || snapshot.cloud?.state === "live") && recentSensorReading(
    snapshot.reading, nowMs, snapshot.activity?.input_age_seconds, snapshot.fetchedAtMs, cloudMode ? 15 : 5,
  );
  const deviceId = snapshot.reading?.device_id ?? snapshot.activity?.prediction?.device_id ??
    (cloudMode ? snapshot.activity?.device_id_filter : null) ?? null;

  return <main className="mx-auto min-h-screen max-w-[1320px] px-4 pb-12 pt-5 sm:px-7 sm:pt-7 lg:px-10">
    <header className="flex flex-wrap items-center justify-between gap-4 border-b border-[#d9e3ec] pb-5">
      <div className="flex min-w-0 items-center gap-3.5">
        <span className="flex h-11 w-11 shrink-0 items-center justify-center rounded-[14px] bg-[#183c60] text-white" aria-hidden="true">
          <svg className="h-7 w-7" viewBox="0 0 32 32" fill="none" stroke="currentColor" strokeWidth="2.1" strokeLinecap="round" strokeLinejoin="round"><path d="M3 17h6l3-8 7 15 4-9h6" /></svg>
        </span>
        <div className="min-w-0"><p className="text-xs font-semibold text-[#54708a]">BCA152 Lab 3</p><h1 className="truncate text-xl font-bold tracking-[-0.025em] text-[#17314d] sm:text-2xl">Activity Monitor</h1></div>
      </div>
      <div className="flex flex-wrap items-center gap-3 text-sm">
        <span className="max-w-[190px] truncate rounded-full border border-[#d6e1ec] bg-white px-3 py-1.5 font-medium text-[#4b647c]" title={deviceId ?? "Device unknown"}>{deviceId ?? "Device unknown"}</span>
        <span className={`inline-flex items-center gap-2 rounded-full px-3 py-1.5 font-semibold ${backendOnline && !backendUnhealthy ? "bg-[#e8f5ef] text-[#226b52]" : "bg-[#f0f3f6] text-[#657488]"}`}>
          <span className={`h-2 w-2 rounded-full ${backendOnline && !backendUnhealthy ? "bg-[#318168]" : "bg-[#9caab8]"}`} aria-hidden="true" />
          {loading ? "Checking server" : cloudMode && snapshot.cloud?.state === "unavailable" ? "Cloud unavailable" :
            cloudMode && snapshot.cloud?.state === "sync_delayed" ? "Sync delayed" :
            cloudMode && snapshot.cloud?.state === "backend_offline" ? "Backend offline" :
            cloudMode && snapshot.cloud?.state === "device_offline" ? "Device offline" :
            cloudMode && snapshot.cloud?.state === "no_data" ? "No sensor data yet" :
            backendUnhealthy ? "Backend unhealthy" : backendOnline ? "Backend online" : "Backend disconnected"}
        </span>
      </div>
    </header>

    <div className="mb-6 mt-8 sm:mb-7 sm:mt-10">
      <p className="text-sm font-medium text-[#56718b]">Live overview</p>
      <p className="mt-1 max-w-2xl text-sm leading-6 text-[#687b90]">Sensor readings and experimental activity predictions from the existing STM32 monitoring system.</p>
    </div>

    <div className="grid gap-5 lg:grid-cols-[minmax(0,1.5fr)_minmax(320px,1fr)] lg:gap-6">
      <ActivityPanel latest={snapshot.activity} current={activity} backendOnline={backendOnline} loading={loading} />
      <SystemPanel health={snapshot.health} backendOnline={backendOnline} sensorFresh={sensorFresh} deviceId={deviceId}
        lastSensorTime={snapshot.reading?.received_at ?? null} cloud={cloudMode ? snapshot.cloud : undefined} />
    </div>

    <div className="mt-5 grid items-start gap-5 lg:mt-6 lg:grid-cols-[minmax(0,1.5fr)_minmax(320px,1fr)] lg:gap-6">
      <SensorPanel reading={snapshot.reading} history={snapshot.readings} fresh={sensorFresh} loading={loading} error={snapshot.errors.reading} nowMs={nowMs} />
      <HistoryPanel history={snapshot.history} loading={loading} error={snapshot.errors.history} />
    </div>

    <footer className="mt-8 border-t border-[#d9e3ec] pt-5 text-xs leading-5 text-[#6c7d90]">
      Activity predictions are experimental. The walking and running model has not been validated for this STM32 sensor and its placement.
    </footer>
  </main>;
}
