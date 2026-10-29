import { createClient } from "@supabase/supabase-js";
import type { IngestStore } from "./ingest";

function admin() {
  const url = process.env.SUPABASE_URL;
  const key = process.env.SUPABASE_SECRET_KEY;
  if (!url || !key) throw new Error("Cloud storage is not configured");
  return createClient(url, key, { auth: { persistSession: false, autoRefreshToken: false } });
}

export const cloudStore: IngestStore = {
  async owner(deviceId) {
    const { data, error } = await admin().from("devices").select("owner_id")
      .eq("device_id", deviceId).eq("enabled", true).maybeSingle();
    if (error) throw error;
    return data?.owner_id ?? null;
  },
  async readings(rows) {
    if (!rows.length) return;
    const { error } = await admin().from("sensor_readings").upsert(rows, {
      onConflict: "device_id,event_id", ignoreDuplicates: true,
    });
    if (error) throw error;
  },
  async predictions(rows) {
    if (!rows.length) return;
    const { error } = await admin().from("activity_predictions").upsert(rows, {
      onConflict: "device_id,event_id", ignoreDuplicates: true,
    });
    if (error) throw error;
  },
  async status(row) {
    const { error } = await admin().from("device_status").upsert(row, { onConflict: "device_id" });
    if (error) throw error;
  },
};
