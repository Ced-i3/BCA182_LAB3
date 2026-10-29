"use client";

import { useState, type FormEvent } from "react";
import { browserClient } from "@/lib/cloud/browser";

export function LoginForm() {
  const [email, setEmail] = useState("");
  const [message, setMessage] = useState("");
  const [busy, setBusy] = useState(false);
  async function submit(event: FormEvent) {
    event.preventDefault();
    setBusy(true);
    const { error } = await browserClient().auth.signInWithOtp({
      email, options: { emailRedirectTo: `${window.location.origin}/auth/callback`, shouldCreateUser: false },
    });
    setMessage(error ? "Could not send a sign-in link. Try again later." : "Check your email for a sign-in link.");
    setBusy(false);
  }
  return <main className="mx-auto flex min-h-screen max-w-md items-center px-4">
    <form onSubmit={submit} className="w-full rounded-[24px] border border-[#dbe4ed] bg-white p-7 shadow-sm">
      <p className="text-sm font-medium text-[#56718b]">BCA152 Lab 3</p>
      <h1 className="mt-1 text-2xl font-bold text-[#17314d]">Activity Monitor</h1>
      <p className="mt-3 text-sm text-[#61758a]">Sign in to view private monitoring data.</p>
      <label htmlFor="email" className="mt-6 block text-sm font-semibold text-[#294663]">Email</label>
      <input id="email" type="email" required value={email} onChange={event => setEmail(event.target.value)}
        className="mt-2 w-full rounded-lg border border-[#cbd9e6] px-3 py-2 text-[#17314d]" />
      <button disabled={busy} className="mt-5 w-full rounded-lg bg-[#183c60] px-4 py-2.5 font-semibold text-white disabled:opacity-50">
        {busy ? "Sending…" : "Send sign-in link"}
      </button>
      {message && <p role="status" className="mt-4 text-sm text-[#54708a]">{message}</p>}
    </form>
  </main>;
}
