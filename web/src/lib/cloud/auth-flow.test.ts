import assert from "node:assert/strict";
import test from "node:test";
import { createClient } from "@supabase/supabase-js";

test("existing-owner email link uses OTP without creating a user", async () => {
  const requests: Array<{ url: URL; body: Record<string, unknown> }> = [];
  const redirect = "https://bca182-lab3-2ibxocoka-ced-i3.vercel.app/auth/callback";
  const client = createClient("https://example.supabase.co", "sb_publishable_test", {
    auth: { flowType: "pkce", persistSession: false, autoRefreshToken: false },
    global: { fetch: async (input, init) => {
      requests.push({ url: new URL(String(input)),
        body: JSON.parse(String(init?.body)) as Record<string, unknown> });
      return new Response("{}", { status: 200, headers: { "Content-Type": "application/json" } });
    } },
  });

  const { error } = await client.auth.signInWithOtp({
    email: "existing@example.invalid",
    options: { emailRedirectTo: redirect, shouldCreateUser: false },
  });

  assert.equal(error, null);
  assert.equal(requests.length, 1);
  assert.equal(requests[0].url.pathname, "/auth/v1/otp");
  assert.equal(requests[0].url.searchParams.get("redirect_to"), redirect);
  assert.equal(requests[0].body.create_user, false);
});
