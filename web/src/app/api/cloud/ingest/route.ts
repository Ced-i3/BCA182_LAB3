import { ingest } from "@/lib/cloud/ingest";
import { cloudStore } from "@/lib/cloud/store";

export async function POST(request: Request) {
  return ingest(request, cloudStore, process.env.CLOUD_INGEST_TOKEN_HASHES);
}
