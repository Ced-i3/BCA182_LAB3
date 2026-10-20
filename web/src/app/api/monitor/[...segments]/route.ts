import { NextRequest, NextResponse } from "next/server.js";
import {
  parseActivityHistory, parseActivityLatest, parseHealth, parseLatestReading,
  parseReadingHistory,
} from "../../../../lib/api/contracts.ts";

const allowedPaths: Record<string, string> = {
  health: "/health",
  latest: "/api/latest",
  history: "/api/history",
  "activity/latest": "/api/activity/latest",
  "activity/history": "/api/activity/history",
};

const timeoutMs = 4000;

function publicResponse(key: string, body: unknown): unknown {
  switch (key) {
    case "health": return parseHealth(body);
    case "latest": return { reading: parseLatestReading(body) };
    case "history": return parseReadingHistory(body);
    case "activity/latest": {
      const latest = parseActivityLatest(body);
      return {
        ...latest,
        reason: ["no_recent_sensor_input", "waiting_for_a_complete_or_fresh_window"].includes(latest.reason ?? "")
          ? latest.reason : latest.reason === null ? null : "inference_service_not_running",
      };
    }
    case "activity/history": return parseActivityHistory(body);
    default: throw new Error("Unknown monitoring endpoint.");
  }
}

function backendOrigin(): URL | null {
  const configured = process.env.BACKEND_URL ??
    (process.env.NODE_ENV === "development" ? "http://127.0.0.1:5000" : null);
  if (!configured) return null;
  try {
    const url = new URL(configured);
    if (!["http:", "https:"].includes(url.protocol) || url.username || url.password ||
        url.pathname !== "/" || url.search || url.hash) return null;
    return url;
  } catch {
    return null;
  }
}

function safeQuery(source: URLSearchParams, key: string): URLSearchParams | null {
  const allowed = new Set(
    key === "history" || key === "activity/history" ? ["limit", "device_id"] :
    key === "activity/latest" ? ["device_id"] : [],
  );
  if (key === "history") allowed.delete("device_id");
  const result = new URLSearchParams();
  for (const [name, value] of source) {
    if (!allowed.has(name) || result.has(name)) return null;
    if (name === "limit" && !/^(?:[1-9]|[1-9][0-9]|100)$/.test(value)) return null;
    if (name === "device_id" && (!value.trim() || value.length > 80)) return null;
    result.set(name, value);
  }
  return result;
}

export async function GET(
  request: NextRequest,
  context: { params: Promise<{ segments: string[] }> },
) {
  const { segments } = await context.params;
  const key = segments.join("/");
  const path = allowedPaths[key];
  if (!path) return NextResponse.json({ error: "Unknown monitoring endpoint." }, { status: 404 });

  const query = safeQuery(request.nextUrl.searchParams, key);
  if (!query) return NextResponse.json({ error: "Invalid monitoring query." }, { status: 400 });

  const origin = backendOrigin();
  if (!origin) {
    return NextResponse.json({ error: "Monitoring backend is not configured." }, { status: 503 });
  }

  const target = new URL(path, origin);
  target.search = query.toString();
  try {
    const response = await fetch(target, {
      cache: "no-store",
      signal: AbortSignal.timeout(timeoutMs),
      headers: { Accept: "application/json" },
    });
    if (!response.headers.get("content-type")?.includes("application/json")) {
      return NextResponse.json({ error: "Monitoring backend returned an invalid response." }, { status: 502 });
    }
    const body: unknown = await response.json();
    const sanitized = publicResponse(key, body);
    return NextResponse.json(sanitized, {
      status: response.status,
      headers: { "Cache-Control": "no-store", "X-Content-Type-Options": "nosniff" },
    });
  } catch (error) {
    const invalid = error instanceof Error && error.message.startsWith("Invalid ") ||
      error instanceof Error && error.message.startsWith("Inconsistent ") ||
      error instanceof Error && error.message.startsWith("Unavailable activity");
    return NextResponse.json(
      { error: invalid ? "Monitoring backend returned an invalid response." : "Cannot connect to monitoring server." },
      { status: 502, headers: { "Cache-Control": "no-store" } },
    );
  }
}
