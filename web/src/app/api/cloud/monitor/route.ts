import { serveCloudMonitor } from "@/lib/cloud/monitor";
import { publicCloudReader } from "@/lib/cloud/public-reader";

export const dynamic = "force-dynamic";

export async function GET(request: Request) {
  if (process.env.CLOUD_MONITOR_MODE !== "cloud") {
    return Response.json({ error: "Cloud monitoring unavailable." },
      { status: 503, headers: { "Cache-Control": "no-store" } });
  }
  return serveCloudMonitor(publicCloudReader, request);
}
