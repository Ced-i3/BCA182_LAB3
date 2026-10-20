import type { ActivityHistoryResponse, ActivityLabel } from "@/lib/api/contracts";
import { localTime } from "@/lib/utils/status";

const labelColors: Record<ActivityLabel, string> = {
  IDLE: "bg-[#edf3f8] text-[#315c7d]",
  WALKING: "bg-[#e7f2fc] text-[#245d95]",
  RUNNING: "bg-[#dcebf8] text-[#1d4f80]",
};

export function HistoryPanel({ history, loading, error }: {
  history: ActivityHistoryResponse | null;
  loading: boolean;
  error: boolean;
}) {
  return <section className="rounded-[24px] border border-[#dbe4ed] bg-white p-6 sm:p-7" aria-labelledby="history-heading">
    <div className="flex items-start justify-between gap-4">
      <div><h2 id="history-heading" className="text-xl font-semibold tracking-tight text-[#18324e]">Activity history</h2>
        <p className="mt-1 text-sm text-[#6c7b8f]">Previous experimental predictions</p></div>
      <span className="rounded-lg bg-[#f2f6fa] px-2.5 py-1 text-xs font-semibold text-[#55708d]">Recent</span>
    </div>
    {history?.predictions.length ? <ol className="mt-5 divide-y divide-[#e8edf2]">
      {history.predictions.map((prediction) => <li key={prediction.id} className="flex items-start gap-3 py-3.5 first:pt-0">
        <span className="mt-1 h-2.5 w-2.5 shrink-0 rounded-full bg-[#3975aa]" aria-hidden="true" />
        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-center justify-between gap-2">
            <span className={`rounded-md px-2 py-1 text-xs font-bold ${labelColors[prediction.activity_label]}`}>{prediction.activity_label}</span>
            <time className="text-xs text-[#6e7d8d]" dateTime={prediction.window_end_timestamp}>{localTime(prediction.window_end_timestamp)}</time>
          </div>
          <p className="mt-1.5 text-xs text-[#718197]">{prediction.detection_method === "RULE_BASED" ? "Motion stability rule" : "Decision Tree"} · {prediction.device_id}</p>
        </div>
      </li>)}
    </ol> : <p className="mt-8 rounded-xl bg-[#f5f7fa] px-4 py-8 text-center text-sm text-[#607286]">
      {loading ? "Loading activity history…" : error ? "Activity history could not be loaded." : "No activity history yet."}
    </p>}
  </section>;
}
