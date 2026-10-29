export function loginMessage(error: { code?: string; status?: number } | null): string {
  if (!error) return "Check your email for a sign-in link.";
  if (error.code === "over_email_send_rate_limit") {
    return "Email limit reached. Wait before requesting another sign-in link. If you already received one, use it before it expires.";
  }
  if (error.status === 429) return "Too many sign-in requests. Please wait before trying again.";
  return "Could not send a sign-in link. Try again later.";
}
