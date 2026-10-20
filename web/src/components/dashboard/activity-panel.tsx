import type { ActivityLabel, ActivityLatestResponse } from "@/lib/api/contracts";
import { localTime } from "@/lib/utils/status";

function ActivityIcon({ activity }: { activity: ActivityLabel | null }) {
  if (activity === "IDLE") {
    return <svg viewBox="0 0 64 64" fill="none" stroke="currentColor" strokeWidth="2.5" aria-hidden="true">
      <circle cx="32" cy="32" r="22" /><path d="M32 18v14l9 6" strokeLinecap="round" strokeLinejoin="round" />
    </svg>;
  }
  if (activity === "WALKING" || activity === "RUNNING") {
    return <svg viewBox="0 0 64 64" fill="none" stroke="currentColor" strokeWidth="2.7" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      <circle cx="37" cy="12" r="4" /><path d={activity === "RUNNING"
        ? "M17 31l15-8 10 7 8-1M32 23l-4 15-14 12m14-12 17 13"
        : "M18 33l13-9 10 6 7-1M31 24l-1 16-11 11m11-11 13 10"} />
    </svg>;
  }
  return <svg viewBox="0 0 64 64" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" aria-hidden="true">
    <path d="M10 33h10l5-12 10 24 7-15h12" />
  </svg>;
}

function unavailableMessage(latest: ActivityLatestResponse | null, backendOnline: boolean, loading: boolean) {
  if (loading) return { title: "Loading activity", detail: "Checking the monitoring server." };
  if (!backendOnline) return { title: "Activity unavailable", detail: "Cannot connect to monitoring server." };
  if (!latest) return { title: "Activity unavailable", detail: "Activity status could not be loaded." };
  if (latest.status === "pending") return { title: "Analyzing sensor data", detail: "Waiting for a complete, recent sensor window." };
  if (latest.reason === "no_recent_sensor_input") return { title: "No recent activity", detail: "Waiting for sensor data. The last prediction is history only." };
  return { title: "Recognition unavailable", detail: "Activity recognition is not ready. Earlier predictions remain in history." };
}

export function ActivityPanel({
  latest, current, backendOnline, loading,
}: {
  latest: ActivityLatestResponse | null;
  current: ActivityLabel | null;
  backendOnline: boolean;
  loading: boolean;
}) {
  const unavailable = unavailableMessage(latest, backendOnline, loading);
  const label = current ?? unavailable.title;
  const lastPrediction = latest?.prediction;

  return <section className="relative overflow-hidden rounded-[28px] border border-[#cbd9e7] bg-white p-6 shadow-[0_12px_40px_-28px_rgba(21,55,90,0.32)] sm:p-8 lg:min-h-[338px]" aria-labelledby="activity-heading">
    <div className="absolute inset-x-0 top-0 h-1 bg-[#1f5b94]" />
    <div className="flex items-start justify-between gap-5">
      <div>
        <h2 id="activity-heading" className="text-sm font-semibold text-[#4e6277]">Current activity</h2>
        <p className="mt-1 text-sm text-[#718197]">Latest experimental prediction</p>
      </div>
      <div className={`flex h-14 w-14 shrink-0 items-center justify-center rounded-2xl ${current ? "bg-[#eaf3fb] text-[#225e97]" : "bg-[#f0f4f8] text-[#8090a3]"}`}>
        <div className="h-9 w-9"><ActivityIcon activity={current} /></div>
      </div>
    </div>
    <div className="mt-8 min-h-28" aria-live="polite">
      <p className={`${current ? "text-5xl font-bold tracking-[-0.045em] text-[#102a46] sm:text-6xl" : "text-3xl font-semibold tracking-[-0.03em] text-[#223a55] sm:text-4xl"}`}>
        {label}
      </p>
      <p className="mt-3 max-w-lg text-sm leading-6 text-[#5e7085]">
        {current ? "Classification is based on the latest complete sensor window." : unavailable.detail}
      </p>
    </div>
    <div className="mt-5 flex flex-wrap gap-x-8 gap-y-3 border-t border-[#e5ebf1] pt-5 text-sm">
      <div><span className="block text-[#6d7c90]">Prediction time</span><span className="mt-1 block font-medium text-[#203a56]">{current && lastPrediction ? localTime(lastPrediction.window_end_timestamp) : "No current prediction"}</span></div>
      <div><span className="block text-[#6d7c90]">Method</span><span className="mt-1 block font-medium text-[#203a56]">{current && lastPrediction ? (lastPrediction.detection_method === "RULE_BASED" ? "Motion stability rule" : "Decision Tree") : "—"}</span></div>
    </div>
    <span className="mt-5 inline-flex rounded-full border border-[#b7d4ed] bg-[#edf6fd] px-3 py-1 text-xs font-semibold text-[#265b8a]">Experimental classification</span>
  </section>;
}
