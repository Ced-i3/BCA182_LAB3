import { NextResponse } from "next/server";
import { cloudConfigured, userClient } from "@/lib/cloud/auth";
import { serveCloudMonitor } from "@/lib/cloud/monitor";

export async function GET() {
  const headers = { "Cache-Control": "private, no-store", "X-Content-Type-Options": "nosniff" };
  if (!cloudConfigured()) return NextResponse.json({ error: "Cloud monitoring unavailable." }, { status: 503, headers });
  let client;
  try { client = await userClient(); }
  catch { return NextResponse.json({ error: "Cloud service unavailable." }, { status: 503, headers }); }
  return serveCloudMonitor({
    async claims() {
      const { data, error } = await client.auth.getClaims();
      return error ? null : data?.claims?.sub ?? null;
    },
    async firstDevice(owner) {
      const { data, error } = await client.from("devices").select("device_id")
        .eq("owner_id", owner).eq("enabled", true).order("device_id").limit(1);
      if (error) throw error;
      return data?.[0]?.device_id ?? null;
    },
    async sensors(owner, device) {
      const { data, error } = await client.from("sensor_readings")
        .select("source_id,device_id,timestamp,received_at,accel_x,accel_y,accel_z,gyro_x,gyro_y,gyro_z")
        .eq("owner_id", owner).eq("device_id", device).order("received_at", { ascending: false }).limit(10);
      if (error) throw error;
      return data ?? [];
    },
    async predictions(owner, device) {
      const { data, error } = await client.from("activity_predictions")
        .select("source_id,device_id,activity_label,activity_code,detection_method,model_version,window_start_timestamp,window_end_timestamp,created_at,experimental")
        .eq("owner_id", owner).eq("device_id", device).order("window_end_timestamp", { ascending: false }).limit(8);
      if (error) throw error;
      return data ?? [];
    },
    async status(owner, device) {
      const { data, error } = await client.from("device_status")
        .select("backend_observed_at,backend_online,mqtt_connected,inference_status,model_loaded,last_sensor_received_at,last_successful_sync_at")
        .eq("owner_id", owner).eq("device_id", device).maybeSingle();
      if (error) throw error;
      return data;
    },
  });
}
