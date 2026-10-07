import "server-only";

import { createHash } from "node:crypto";
import { cookies } from "next/headers";

import { serverEnv } from "@/lib/server/env";

export interface SessionUser {
  id: string;
  email: string;
  name: string;
  emailVerified: boolean;
  twoFactorEnabled?: boolean | null;
}

export interface Session {
  user: SessionUser;
  session: { id: string; activeOrganizationId?: string | null };
}

/** Changes whenever the client switches or creates an organization (busts the token cache). */
export const ORG_EPOCH_COOKIE = "org_epoch";
const TOKEN_TTL_MS = 30_000;
const tokens = new Map<string, { token: string; expires: number }>();

export async function cookieHeader(): Promise<string> {
  return (await cookies()).toString();
}

export async function getSession(cookie?: string): Promise<Session | null> {
  const header = cookie ?? (await cookieHeader());
  if (!header) return null;
  const response = await fetch(`${serverEnv.authUrl}/api/auth/get-session`, {
    headers: { cookie: header },
    cache: "no-store",
  });
  if (!response.ok) return null;
  const body = (await response.json()) as Session | null;
  return body?.user ? body : null;
}

/**
 * Short-lived API token for the signed-in user, minted by the auth service and cached briefly per session
 * (and per organization epoch). It never leaves the server.
 */
export async function getApiToken(cookie: string): Promise<string | null> {
  if (!cookie) return null;
  const key = createHash("sha256").update(cookie).digest("hex");
  const cached = tokens.get(key);
  if (cached && cached.expires > Date.now()) return cached.token;
  const response = await fetch(`${serverEnv.authUrl}/api/auth/token`, {
    headers: { cookie },
    cache: "no-store",
  });
  if (!response.ok) {
    tokens.delete(key);
    return null;
  }
  const { token } = (await response.json()) as { token: string };
  tokens.set(key, { token, expires: Date.now() + TOKEN_TTL_MS });
  if (tokens.size > 5000) tokens.clear(); // bound memory; tokens are cheap to re-mint
  return token;
}
