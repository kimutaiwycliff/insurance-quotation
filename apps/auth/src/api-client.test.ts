import { describe, expect, it, vi } from "vitest";

import { createApiNotifier } from "./api-client.js";
import type { Config } from "./config.js";

const config = { apiInternalUrl: "http://api.test" } as Config;

describe("createApiNotifier", () => {
  it("sends a signed JSON request", async () => {
    const fetchImpl = vi.fn(async () => new Response(null, { status: 204 }));
    await createApiNotifier(config, async () => "tok", fetchImpl).post("/internal/v1/x", { a: 1 }, "PUT");
    expect(fetchImpl).toHaveBeenCalledOnce();
    const [url, init] = fetchImpl.mock.calls[0] as unknown as [string, RequestInit];
    expect(url).toBe("http://api.test/internal/v1/x");
    expect(init.method).toBe("PUT");
    expect((init.headers as Record<string, string>).authorization).toBe("Bearer tok");
    expect(init.body).toBe('{"a":1}');
  });

  it("retries server errors, then gives up without throwing", async () => {
    const fetchImpl = vi.fn(async () => new Response(null, { status: 503 }));
    const log = vi.spyOn(console, "error").mockImplementation(() => {});
    await createApiNotifier(config, async () => "tok", fetchImpl).post("/x", {});
    expect(fetchImpl).toHaveBeenCalledTimes(3);
    expect(log).toHaveBeenCalledOnce();
  });

  it("does not retry client errors", async () => {
    const fetchImpl = vi.fn(async () => new Response(null, { status: 422 }));
    vi.spyOn(console, "error").mockImplementation(() => {});
    await createApiNotifier(config, async () => "tok", fetchImpl).post("/x", {});
    expect(fetchImpl).toHaveBeenCalledOnce();
  });
});
