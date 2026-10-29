import { MonitorDashboard } from "@/components/dashboard/monitor-dashboard";
import { redirect } from "next/navigation";
import { cloudConfigured, userClient } from "@/lib/cloud/auth";

export default async function Home() {
  const cloudMode = cloudConfigured();
  if (cloudMode) {
    const client = await userClient();
    const { data } = await client.auth.getClaims();
    if (!data?.claims) redirect("/login");
  }
  return <MonitorDashboard cloudMode={cloudMode} />;
}
