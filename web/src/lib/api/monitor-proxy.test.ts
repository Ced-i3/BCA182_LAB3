import assert from "node:assert/strict";
import test from "node:test";
import { NextRequest } from "next/server.js";
import { GET } from "../../app/api/monitor/[...segments]/route.ts";

function callRoute(segments: string[]) {
  const request = new NextRequest(`http://127.0.0.1/api/monitor/${segments.join("/")}`);
  return GET(request, { params: Promise.resolve({ segments }) });
}

async function withProductionEnvironment(
  backendUrl: string | undefined,
  fetchImplementation: typeof fetch,
  run: () => Promise<void>,
) {
  const environment = process.env as unknown as Record<string, string | undefined>;
  const previousNodeEnv = environment.NODE_ENV;
  const previousBackendUrl = environment.BACKEND_URL;
  const previousFetch = globalThis.fetch;

  environment.NODE_ENV = "production";
  if (backendUrl === undefined) delete environment.BACKEND_URL;
  else environment.BACKEND_URL = backendUrl;
  globalThis.fetch = fetchImplementation;

  try {
    await run();
  } finally {
    if (previousNodeEnv === undefined) delete environment.NODE_ENV;
    else environment.NODE_ENV = previousNodeEnv;
    if (previousBackendUrl === undefined) delete environment.BACKEND_URL;
    else environment.BACKEND_URL = previousBackendUrl;
    globalThis.fetch = previousFetch;
  }
}

test("production proxy reports backend unavailable when BACKEND_URL is unset", async () => {
  let upstreamCalls = 0;

  await withProductionEnvironment(undefined, async () => {
    upstreamCalls += 1;
    return new Response(null, { status: 200 });
  }, async () => {
    const response = await callRoute(["health"]);

    assert.equal(response.status, 503);
    assert.equal((await response.json()).error, "Monitoring backend is not configured.");
    assert.equal(upstreamCalls, 0);
  });
});

test("proxy rejects paths outside its five endpoint allowlist", async () => {
  let upstreamCalls = 0;

  await withProductionEnvironment("http://127.0.0.1:5000", async () => {
    upstreamCalls += 1;
    return new Response(null, { status: 200 });
  }, async () => {
    const response = await callRoute(["admin", "delete"]);

    assert.equal(response.status, 404);
    assert.equal(upstreamCalls, 0);
  });
});

test("proxy converts an unreachable backend into an unavailable response", async () => {
  await withProductionEnvironment("http://127.0.0.1:5000", async () => {
    throw new TypeError("fetch failed");
  }, async () => {
    const response = await callRoute(["health"]);

    assert.equal(response.status, 502);
    assert.equal((await response.json()).error, "Cannot connect to monitoring server.");
    assert.equal(response.headers.get("cache-control"), "no-store");
  });
});

test("proxy rejects non-JSON backend responses without exposing their body", async () => {
  await withProductionEnvironment("http://127.0.0.1:5000", async () => new Response(
    "private backend error page",
    { status: 200, headers: { "content-type": "text/html" } },
  ), async () => {
    const response = await callRoute(["health"]);
    const body = await response.json();

    assert.equal(response.status, 502);
    assert.equal(body.error, "Monitoring backend returned an invalid response.");
    assert.equal(JSON.stringify(body).includes("private backend error page"), false);
  });
});
