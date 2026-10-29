import { cloudSnapshot } from "./snapshot.ts";

export const PUBLIC_DEVICE_ID = "rt-spark-001";
const responseHeaders = { "Cache-Control": "public, max-age=0, s-maxage=3, must-revalidate",
  "X-Content-Type-Options": "nosniff" };
const errorHeaders = { "Cache-Control": "no-store", "X-Content-Type-Options": "nosniff" };
type Row = Record<string, unknown>;

export interface PublicCloudReader {
  registered(device: string): Promise<boolean>;
  sensors(device: string): Promise<Row[]>;
  predictions(device: string): Promise<Row[]>;
  status(device: string): Promise<Row | null>;
}

export async function serveCloudMonitor(reader: PublicCloudReader, request: Request): Promise<Response> {
  if (new URL(request.url).search) {
    return Response.json({ error: "Query parameters are not supported." }, { status: 400, headers: errorHeaders });
  }
  try {
    if (!await reader.registered(PUBLIC_DEVICE_ID)) {
      return Response.json({ error: "Monitoring unavailable." }, { status: 503, headers: errorHeaders });
    }
    const [sensors, predictions, status] = await Promise.all([
      reader.sensors(PUBLIC_DEVICE_ID), reader.predictions(PUBLIC_DEVICE_ID), reader.status(PUBLIC_DEVICE_ID),
    ]);
    return Response.json(cloudSnapshot(PUBLIC_DEVICE_ID,
      sensors.filter(row => row.device_id === PUBLIC_DEVICE_ID).slice(0, 10),
      predictions.filter(row => row.device_id === PUBLIC_DEVICE_ID).slice(0, 8), status),
      { headers: responseHeaders });
  } catch {
    return Response.json({ error: "Cloud service unavailable." }, { status: 503, headers: errorHeaders });
  }
}
