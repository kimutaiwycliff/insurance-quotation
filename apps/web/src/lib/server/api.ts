import "server-only";

import { serverEnv } from "@/lib/server/env";
import { cookieHeader, getApiToken } from "@/lib/server/session";
import { ApiError, parseProblem } from "@/lib/problem";

/** Server-side API call for server components (token attached here; nothing reaches the browser). */
export async function serverApi<T>(path: string, init: RequestInit = {}): Promise<T> {
  const token = await getApiToken(await cookieHeader());
  if (!token) throw new ApiError({ status: 401, code: "unauthenticated", title: "Sign in again" });
  const response = await fetch(`${serverEnv.apiUrl}${path}`, {
    ...init,
    headers: { ...(init.headers as Record<string, string>), authorization: `Bearer ${token}` },
    cache: "no-store",
  });
  if (!response.ok) throw new ApiError(await parseProblem(response));
  return (await response.json()) as T;
}
