import assert from "node:assert/strict";
import test from "node:test";
import { loginMessage } from "./login-message.ts";

test("email send limit has a useful message without exposing Auth details", () => {
  const message = loginMessage({ code: "over_email_send_rate_limit", status: 429 });
  assert.match(message, /wait before requesting another sign-in link/i);
  assert.doesNotMatch(message, /account|password|token/i);
  assert.match(loginMessage({ status: 429 }), /too many sign-in requests/i);
});

test("other Auth failures stay generic", () => {
  assert.equal(loginMessage(null), "Check your email for a sign-in link.");
  assert.equal(loginMessage({ code: "some_other_error", status: 400 }),
    "Could not send a sign-in link. Try again later.");
});
