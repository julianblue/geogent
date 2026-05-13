import "server-only";
import { cookies } from "next/headers";
import { redirect } from "next/navigation";

const COOKIE_NAME = "geogent_session";
const BACKEND_URL = process.env.BACKEND_URL ?? "http://localhost:8000";

export type SessionUser = {
  id: number;
  email: string;
  is_active: boolean;
  created_at: string;
};

export type Session = { user: SessionUser };

export type SignInResult = { ok: true } | { ok: false; error: string };

export async function signIn(email: string, password: string): Promise<SignInResult> {
  let res: Response;
  try {
    res = await fetch(`${BACKEND_URL}/api/v1/auth/login`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ email, password }),
      cache: "no-store",
    });
  } catch {
    return { ok: false, error: "Could not reach the server. Please try again." };
  }
  if (!res.ok) {
    if (res.status === 401) return { ok: false, error: "Invalid email or password." };
    return { ok: false, error: "Login failed. Please try again." };
  }
  const body = (await res.json()) as { access_token: string; expires_in: number };
  cookies().set(COOKIE_NAME, body.access_token, {
    httpOnly: true,
    secure: process.env.NODE_ENV === "production",
    sameSite: "lax",
    path: "/",
    maxAge: body.expires_in,
  });
  return { ok: true };
}

export async function signOut(): Promise<void> {
  cookies().delete(COOKIE_NAME);
  redirect("/login");
}

type GetSessionResult =
  | { kind: "ok"; user: SessionUser }
  | { kind: "missing" }
  | { kind: "invalid" }
  | { kind: "unreachable" };

async function readSession(): Promise<GetSessionResult> {
  const token = cookies().get(COOKIE_NAME)?.value;
  if (!token) return { kind: "missing" };
  let res: Response;
  try {
    res = await fetch(`${BACKEND_URL}/api/v1/auth/me`, {
      headers: { Authorization: `Bearer ${token}` },
      cache: "no-store",
    });
  } catch {
    return { kind: "unreachable" };
  }
  if (res.status === 401 || res.status === 403) return { kind: "invalid" };
  if (!res.ok) return { kind: "unreachable" };
  const user = (await res.json()) as SessionUser;
  return { kind: "ok", user };
}

export async function getSession(): Promise<Session | null> {
  const result = await readSession();
  return result.kind === "ok" ? { user: result.user } : null;
}

export async function requireSession(): Promise<Session> {
  const result = await readSession();
  if (result.kind === "ok") return { user: result.user };
  // Server components can't mutate cookies. If the cookie is stale, bounce via
  // the logout route handler which clears it and then redirects to /login.
  if (result.kind === "invalid") redirect("/api/auth/logout");
  redirect("/login");
}

export function getAuthToken(): string | null {
  return cookies().get(COOKIE_NAME)?.value ?? null;
}
