/**
 * Backend-for-frontend: the browser calls /bff/api/v1/..., this attaches the user's API token server-side and
 * forwards to the core API. Only /api/v1/* paths are forwarded; the token never reaches the browser.
 */
import type { NextRequest } from "next/server";

import { serverEnv } from "@/lib/server/env";
import { forwardRequestHeaders, forwardResponse } from "@/lib/server/proxy";
import { getApiToken } from "@/lib/server/session";

const FORWARDED = new Set(["accept", "content-type", "if-match", "idempotency-key", "x-request-id"]);
const SAFE_PATH = /^\/api\/v1\/[A-Za-z0-9._~\-/]*$/;

async function handle(request: NextRequest): Promise<Response> {
  const url = new URL(request.url);
  const path = url.pathname.replace(/^\/bff/, "");
  if (!SAFE_PATH.test(path) || path.includes("..")) {
    return Response.json({ code: "not_found", title: "Not found", status: 404 }, { status: 404 });
  }
  const token = await getApiToken(request.headers.get("cookie") ?? "");
  if (!token) {
    return Response.json(
      { code: "unauthenticated", title: "Sign in again", status: 401 },
      { status: 401, headers: { "content-type": "application/problem+json" } },
    );
  }
  const headers = forwardRequestHeaders(request.headers, FORWARDED);
  headers.set("authorization", `Bearer ${token}`);
  const forwardedFor = request.headers.get("x-forwarded-for");
  if (forwardedFor) headers.set("x-forwarded-for", forwardedFor);
  const upstream = await fetch(`${serverEnv.apiUrl}${path}${url.search}`, {
    method: request.method,
    headers,
    body: ["GET", "HEAD"].includes(request.method) ? undefined : await request.arrayBuffer(),
    cache: "no-store",
    redirect: "manual",
  });
  return forwardResponse(upstream);
}

export const GET = handle;
export const POST = handle;
export const PUT = handle;
export const PATCH = handle;
export const DELETE = handle;
