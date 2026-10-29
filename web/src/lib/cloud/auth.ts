import { createServerClient } from "@supabase/ssr";
import { cookies } from "next/headers";

export function cloudConfigured(): boolean {
  return process.env.CLOUD_MONITOR_MODE === "cloud" &&
    Boolean(process.env.NEXT_PUBLIC_SUPABASE_URL && process.env.NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY);
}

export async function userClient() {
  const cookieStore = await cookies();
  const url = process.env.NEXT_PUBLIC_SUPABASE_URL;
  const key = process.env.NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY;
  if (!url || !key) throw new Error("Cloud Auth is not configured");
  return createServerClient(url, key, {
    cookies: {
      getAll() { return cookieStore.getAll(); },
      setAll(values) {
        try { values.forEach(({ name, value, options }) => cookieStore.set(name, value, options)); }
        catch { /* Server Component cannot set cookies; the Next proxy refreshes them. */ }
      },
    },
  });
}
