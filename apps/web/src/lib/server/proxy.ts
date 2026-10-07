import "server-only";

/** Hop-by-hop and sensitive headers never forwarded between the browser and internal services. */
const DROP_REQUEST = new Set(["host", "connection", "content-length", "transfer-encoding", "keep-alive", "upgrade"]);
const DROP_RESPONSE = new Set(["connection", "transfer-encoding", "keep-alive", "content-encoding", "content-length"]);

export function forwardRequestHeaders(source: Headers, allow?: ReadonlySet<string>): Headers {
  const headers = new Headers();
  source.forEach((value, key) => {
    const name = key.toLowerCase();
    if (DROP_REQUEST.has(name)) return;
    if (allow && !allow.has(name)) return;
    headers.set(key, value);
  });
  return headers;
}

export function forwardResponse(upstream: Response): Response {
  const headers = new Headers();
  upstream.headers.forEach((value, key) => {
    if (!DROP_RESPONSE.has(key.toLowerCase()) && key.toLowerCase() !== "set-cookie") headers.set(key, value);
  });
  for (const cookie of upstream.headers.getSetCookie()) headers.append("set-cookie", cookie);
  return new Response(upstream.body, { status: upstream.status, statusText: upstream.statusText, headers });
}
