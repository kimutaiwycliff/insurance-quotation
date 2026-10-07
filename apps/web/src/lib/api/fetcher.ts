/**
 * Browser-side fetcher used by the generated API client (orval mutator).
 *
 * Requests go to the Next.js BFF (`/bff/api/v1/...`), which attaches the API token server-side, so the browser
 * never holds it (ADR-0006 §7). Mutations get an Idempotency-Key automatically; errors are RFC 9457 problems.
 */
import { ApiError, parseProblem } from "@/lib/problem";
import { randomId } from "@/lib/utils";


export const BFF_PREFIX = "/bff";

const MUTATING = new Set(["POST", "PUT", "PATCH", "DELETE"]);

export async function apiFetch<T>(url: string, options: RequestInit = {}): Promise<T> {
  const method = (options.method ?? "GET").toUpperCase();
  const headers = new Headers(options.headers);
  if (method === "POST" && !headers.has("Idempotency-Key")) {
    headers.set("Idempotency-Key", randomId());
  }
  if (options.body && !headers.has("Content-Type")) headers.set("Content-Type", "application/json");
  const response = await fetch(`${BFF_PREFIX}${url}`, {
    ...options,
    method,
    headers,
    credentials: "same-origin",
    cache: MUTATING.has(method) ? "no-store" : options.cache,
  });
  if (!response.ok) throw new ApiError(await parseProblem(response));
  if (response.status === 204) return undefined as T;
  return (await response.json()) as T;
}

/** ETag for If-Match from a resource's `version` (the API's ETag is W/"<version>"). */
export function ifMatch(version: number): { headers: { "If-Match": string } } {
  return { headers: { "If-Match": `W/"${version}"` } };
}

export default apiFetch;

/** Raw BFF call for non-JSON responses (HTML previews, PDFs). Throws ApiError like apiFetch. */
export async function bffRaw(url: string, init: RequestInit = {}): Promise<Response> {
  const headers = new Headers(init.headers);
  if (init.body && !headers.has("Content-Type")) headers.set("Content-Type", "application/json");
  const response = await fetch(`${BFF_PREFIX}${url}`, { ...init, headers, credentials: "same-origin" });
  if (!response.ok) throw new ApiError(await parseProblem(response));
  return response;
}
