"use client";
import { browserClient } from "@/lib/cloud/browser";
import { useRouter } from "next/navigation";

export function SignOut() {
  const router = useRouter();
  return <button className="text-sm font-semibold text-[#54708a] underline" onClick={async () => {
    await browserClient().auth.signOut();
    router.push("/login");
    router.refresh();
  }}>Sign out</button>;
}
