import type { HealthResponse } from "@/lib/api/contracts";
import { localTime } from "@/lib/utils/status";

function StatusRow({ label, value, good }: { label: string; value: string; good?: boolean }) {
  return <div className="flex items-start justify-between gap-5 border-b border-[#e8edf2] py-3.5 last:border-0">
    <dt className="text-sm text-[#61758a]">{label}</dt>
    <dd className="flex max-w-[58%] items-center gap-2 text-right text-sm font-semibold text-[#294663]">
      {good !== undefined && <span className={`h-2 w-2 shrink-0 rounded-full ${good ? "bg-[#318168]" : "bg-[#9aa7b5]"}`} aria-hidden="true" />}
      <span>{value}</span>
    </dd>
  </div>;
}

export function SystemPanel({ health, backendOnline, sensorFresh, deviceId, lastSensorTime, cloud }: {
  health: HealthResponse | null;
  backendOnline: boolean;
  sensorFresh: boolean;
  deviceId: string | null;
  lastSensorTime: string | null;
  cloud?: { state: string; lastSyncAt: string | null; lastBackendAt: string | null };
}) {
  const inference = health?.activity_inference;
  return <section className="rounded-[24px] border border-[#dbe4ed] bg-white p-6 sm:p-7" aria-labelledby="system-heading">
    <h2 id="system-heading" className="text-xl font-semibold tracking-tight text-[#18324e]">System status</h2>
    <p className="mt-1 text-sm text-[#6c7b8f]">Connection and reporting state</p>
    <dl className="mt-5">
      <StatusRow label="Monitoring server" value={cloud?.state === "backend_offline" ? "Backend offline" :
        cloud?.state === "sync_delayed" ? "Status delayed" : cloud?.state === "unavailable" ? "Cloud unavailable" :
        health?.status === "unhealthy" ? "Database unavailable" : backendOnline ? "Responding" : "Disconnected"}
        good={backendOnline && health?.status !== "unhealthy" && (!cloud || cloud.state === "live")} />
      <StatusRow label="MQTT subscriber" value={health ? (health.mqtt_connected ? "Connected" : "Disconnected") : "Unknown"} good={health?.mqtt_connected ?? false} />
      <StatusRow label="Sensor reports" value={sensorFresh ? "Recent data" : "No recent data"} good={sensorFresh} />
      <StatusRow label="Inference worker" value={inference ? (inference.status === "running" && inference.model_loaded ? "Running" : "Unavailable") : "Unknown"} good={inference?.status === "running" && inference.model_loaded} />
      <StatusRow label="Device ID" value={deviceId ?? "Not known"} />
      {cloud && <StatusRow label="Cloud sync" value={cloud.state === "live" ? "Current" :
        cloud.state === "sync_delayed" ? "Delayed" : cloud.state === "unavailable" ? "Unavailable" : "Waiting"}
        good={cloud.state === "live"} />}
      {cloud && <StatusRow label="Last synchronized" value={localTime(cloud.lastSyncAt)} />}
    </dl>
    <p className="mt-4 text-xs leading-5 text-[#758397]">Last sensor report: {localTime(lastSensorTime)}. A reachable server does not confirm that the STM32 is streaming.</p>
  </section>;
}
