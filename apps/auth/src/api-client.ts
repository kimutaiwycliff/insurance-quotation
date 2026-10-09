/**
 * Calls the API's internal endpoints from organization hooks (ADR-0006).
 *
 * Requests carry a 60-second service token signed with this service's JWKS (aud = AUTH_INTERNAL_AUDIENCE,
 * sub = "service:auth"). Failures are retried briefly, then logged: the API provisions lazily on the first
 * request anyway, so a missed hook delays nothing that matters.
 */
import type { Config } from "./config.js";

export type ServiceTokenSigner = () => Promise<string>;

export interface ApiNotifier {
  post(path: string, body: unknown, method?: "POST" | "PUT"): Promise<void>;
  /** One call whose answer matters (e.g. a seat check): the HTTP status, or null if the API is unreachable. */
  ask(path: string, body: unknown): Promise<number | null>;
}

const RETRY_DELAYS_MS = [0, 250, 1000];

export function createApiNotifier(
  config: Config,
  signToken: ServiceTokenSigner,
  fetchImpl: typeof fetch = fetch,
): ApiNotifier {
  return {
    async post(path, body, method = "POST") {
      let lastError: unknown;
      for (const delay of RETRY_DELAYS_MS) {
        if (delay) await new Promise((resolve) => setTimeout(resolve, delay));
        try {
          const response = await fetchImpl(`${config.apiInternalUrl}${path}`, {
            method,
            headers: {
              "content-type": "application/json",
              authorization: `Bearer ${await signToken()}`,
            },
            body: JSON.stringify(body),
            signal: AbortSignal.timeout(5000),
          });
          if (response.ok) return;
          lastError = new Error(`API ${method} ${path} returned ${response.status}`);
          if (response.status < 500) break; // a client error will not fix itself
        } catch (error) {
          lastError = error;
        }
      }
      console.error(
        JSON.stringify({ level: "error", event: "api_hook_failed", path, error: String(lastError) }),
      );
    },
    async ask(path, body) {
      try {
        const response = await fetchImpl(`${config.apiInternalUrl}${path}`, {
          method: "POST",
          headers: { "content-type": "application/json", authorization: `Bearer ${await signToken()}` },
          body: JSON.stringify(body),
          signal: AbortSignal.timeout(5000),
        });
        return response.status;
      } catch (error) {
        console.error(JSON.stringify({ level: "error", event: "api_ask_failed", path, error: String(error) }));
        return null;
      }
    },
  };
}
