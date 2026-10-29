import { redirect } from "next/navigation";
import { cloudConfigured, userClient } from "@/lib/cloud/auth";
import { LoginForm } from "./login-form";

export default async function LoginPage() {
  if (!cloudConfigured()) redirect("/");
  const client = await userClient();
  const { data } = await client.auth.getClaims();
  if (data?.claims) redirect("/");
  return <LoginForm />;
}
