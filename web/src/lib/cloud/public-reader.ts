import { createClient } from "@supabase/supabase-js";
import type { PublicCloudReader } from "./monitor";

function client() {
  const url = process.env.SUPABASE_URL;
  const key = process.env.SUPABASE_SECRET_KEY;
  if (!url || !key) throw new Error("Cloud storage is not configured");
  return createClient(url, key, { auth: { persistSession: false, autoRefreshToken: false } });
}

export const publicCloudReader: PublicCloudReader = {
  async registered(device) {
    const { data, error } = await client().from("devices").select("device_id")
      .eq("device_id", device).eq("enabled", true).maybeSingle();
    if (error) throw error;
    return data?.device_id === device;
  },
  async sensors(device) {
    const { data, error } = await client().from("sensor_readings")
      .select("source_id,device_id,timestamp,received_at,accel_x,accel_y,accel_z,gyro_x,gyro_y,gyro_z")
      .eq("device_id", device).order("received_at", { ascending: false }).limit(10);
    if (error) throw error;
    return data ?? [];
  },
  async predictions(device) {
    const { data, error } = await client().from("activity_predictions")
      .select("source_id,device_id,activity_label,activity_code,detection_method,model_version,window_start_timestamp,window_end_timestamp,created_at,experimental")
      .eq("device_id", device).order("window_end_timestamp", { ascending: false }).limit(8);
    if (error) throw error;
    return data ?? [];
  },
  async status(device) {
    const { data, error } = await client().from("device_status")
      .select("backend_observed_at,backend_online,mqtt_connected,inference_status,model_loaded,last_sensor_received_at,last_successful_sync_at")
      .eq("device_id", device).maybeSingle();
    if (error) throw error;
    return data;
  },
};
