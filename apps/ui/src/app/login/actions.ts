"use server";

import { redirect } from "next/navigation";

import { signIn } from "@/lib/auth";

export type LoginActionState = { error?: string };

export async function loginAction(
  _prev: LoginActionState | undefined,
  formData: FormData,
): Promise<LoginActionState> {
  const email = String(formData.get("email") ?? "").trim();
  const password = String(formData.get("password") ?? "");

  if (!email || !password) {
    return { error: "Email and password are required." };
  }

  const result = await signIn(email, password);
  if (!result.ok) {
    return { error: result.error };
  }
  redirect("/app");
}
