import type { ReadingHistoryResponse, SensorReading } from "@/lib/api/contracts";
import { localTime } from "@/lib/utils/status";

function Vector({ values, unit }: { values: { x: number; y: number; z: number }; unit: string }) {
  return <div className="grid grid-cols-3 gap-1 sm:gap-3">
    {(["x", "y", "z"] as const).map((axis) => <div key={axis} className="min-w-0 rounded-xl bg-[#f4f7fa] px-2 py-3 sm:px-4">
      <div className="text-xs font-semibold text-[#62758a]">{axis.toUpperCase()} axis</div>
      <div className="mt-1 truncate font-mono text-base font-semibold tabular-nums tracking-tight text-[#1d3d5d] sm:text-xl" title={`${values[axis]} ${unit}`}>
        {values[axis].toFixed(3)}
      </div>
    </div>)}
  </div>;
}

export function SensorPanel({ reading, history, fresh, loading, error, nowMs }: {
  reading: SensorReading | null;
  history: ReadingHistoryResponse | null;
  fresh: boolean;
  loading: boolean;
  error: boolean;
  nowMs: number;
}) {
  const reports = reading && history ? history.readings.filter((item) =>
    item.device_id === reading.device_id &&
    nowMs - Date.parse(item.received_at) >= 0 &&
    nowMs - Date.parse(item.received_at) <= 10000).length : null;
  return <section className="rounded-[24px] border border-[#dbe4ed] bg-white p-6 sm:p-7" aria-labelledby="sensor-heading">
    <div className="flex flex-wrap items-start justify-between gap-3">
      <div><h2 id="sensor-heading" className="text-xl font-semibold tracking-tight text-[#18324e]">Motion sensor</h2>
        <p className="mt-1 text-sm text-[#6c7b8f]">ICM20608 six-axis measurement</p></div>
      <span className={`rounded-full px-3 py-1 text-xs font-semibold ${fresh ? "bg-[#e5f5ef] text-[#216b50]" : "bg-[#f0f3f6] text-[#617185]"}`}>
        {fresh ? "Recent sensor report" : "No recent sensor report"}
      </span>
    </div>
    {reading ? <>
      {!fresh && <p className="mt-5 rounded-xl bg-[#f5f7fa] px-4 py-3 text-sm text-[#607286]">Values below are the last recorded sample, not live measurements.</p>}
      <div className="mt-6 space-y-6">
        <div><div className="mb-3 flex items-baseline justify-between gap-3"><h3 className="font-semibold text-[#2b4662]">Acceleration</h3><span className="text-xs text-[#6b7b8d]">m/s²</span></div><Vector values={reading.accel_m_s2} unit="m/s²" /></div>
        <div><div className="mb-3 flex items-baseline justify-between gap-3"><h3 className="font-semibold text-[#2b4662]">Angular velocity</h3><span className="text-xs text-[#6b7b8d]">rad/s</span></div><Vector values={reading.gyro_rad_s} unit="rad/s" /></div>
      </div>
      <div className="mt-6 grid gap-2 border-t border-[#e5ebf1] pt-5 text-sm text-[#5e7185] sm:grid-cols-2">
        <p>Captured <span className="font-medium text-[#294663]">{localTime(reading.timestamp)}</span></p>
        <p>Device <span className="font-medium text-[#294663]">{reading.device_id}</span></p>
        {reports !== null && <p className="sm:col-span-2">Recent reports in the last 10 seconds: <span className="font-medium text-[#294663]">{reports}</span></p>}
      </div>
    </> : <p className="mt-8 rounded-xl bg-[#f5f7fa] px-4 py-8 text-center text-sm text-[#607286]">
      {loading ? "Loading sensor readings…" : error ? "Sensor readings could not be loaded." : "Waiting for sensor data."}
    </p>}
  </section>;
}
