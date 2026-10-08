/**
 * Anonymous proxy to the API's token-scoped public routes (/api/v1/public/*): document links and unsubscribe.
 * No credentials are attached; the visitor's IP is passed on for per-IP rate limits and view counting.
 */
import type { NextRequest } from "next/server";

import { serverEnv } from "@/lib/server/env";
import { forwardRequestHeaders, forwardResponse } from "@/lib/server/proxy";

const SAFE = /^\/(links|unsubscribe)\/[A-Za-z0-9_\-.]{10,400}(\/(html|download|beacon|accept|decline))?$/;
const FORWARDED = new Set(["accept", "content-type", "user-agent"]);

async function handle(request: NextRequest): Promise<Response> {
  const url = new URL(request.url);
  const path = url.pathname.replace(/^\/public-api/, "");
  if (!SAFE.test(path)) return Response.json({ code: "not_found", title: "Not found", status: 404 }, { status: 404 });
  const headers = forwardRequestHeaders(request.headers, FORWARDED);
  const forwardedFor = request.headers.get("x-forwarded-for") ?? request.headers.get("x-real-ip");
  if (forwardedFor) headers.set("x-forwarded-for", forwardedFor);
  const upstream = await fetch(`${serverEnv.apiUrl}/api/v1/public${path}`, {
    method: request.method,
    headers,
    body: request.method === "POST" ? await request.arrayBuffer() : undefined,
    redirect: "manual",
    cache: "no-store",
  });
  return forwardResponse(upstream);
}

export const GET = handle;
export const POST = handle;
