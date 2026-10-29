import { cloudSnapshot } from "./snapshot.ts";

type Row = Record<string, unknown>;
export interface CloudReader {
  claims(): Promise<string | null>;
  firstDevice(owner: string): Promise<string | null>;
  sensors(owner: string, device: string): Promise<Row[]>;
  predictions(owner: string, device: string): Promise<Row[]>;
  status(owner: string, device: string): Promise<Row | null>;
}

export async function serveCloudMonitor(reader: CloudReader): Promise<Response> {
  const headers = { "Cache-Control": "private, no-store", "X-Content-Type-Options": "nosniff" };
  try {
    const owner = await reader.claims();
    if (!owner) return Response.json({ error: "Sign-in required." }, { status: 401, headers });
    const device = await reader.firstDevice(owner);
    if (!device) return Response.json({ error: "No device assigned." }, { status: 403, headers });
    const [sensors, predictions, status] = await Promise.all([
      reader.sensors(owner, device), reader.predictions(owner, device), reader.status(owner, device),
    ]);
    return Response.json(cloudSnapshot(device, sensors, predictions, status), { headers });
  } catch {
    return Response.json({ error: "Cloud service unavailable." }, { status: 503, headers });
  }
}
