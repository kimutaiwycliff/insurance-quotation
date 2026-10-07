/**
 * Same-origin proxy to the auth service (Better Auth), so its cookies belong to this site (ADR-0006 §7).
 * The destination is fixed by configuration; only /api/auth/* is reachable.
 */
import type { NextRequest } from "next/server";

import { serverEnv } from "@/lib/server/env";
import { forwardRequestHeaders, forwardResponse } from "@/lib/server/proxy";

async function handle(request: NextRequest): Promise<Response> {
  const url = new URL(request.url);
  const target = `${serverEnv.authUrl}${url.pathname}${url.search}`;
  const headers = forwardRequestHeaders(request.headers);
  headers.set("x-forwarded-host", url.host);
  headers.set("x-forwarded-proto", url.protocol.replace(":", ""));
  const upstream = await fetch(target, {
    method: request.method,
    headers,
    body: request.method === "GET" || request.method === "HEAD" ? undefined : await request.arrayBuffer(),
    redirect: "manual",
    cache: "no-store",
  });
  return forwardResponse(upstream);
}

export const GET = handle;
export const POST = handle;
