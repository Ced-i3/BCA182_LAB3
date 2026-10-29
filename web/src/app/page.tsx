import { MonitorDashboard } from "@/components/dashboard/monitor-dashboard";

export default function Home() {
  return <MonitorDashboard cloudMode={process.env.CLOUD_MONITOR_MODE === "cloud"} />;
}
