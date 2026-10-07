import { afterEach, describe, expect, it } from "vitest";

import { loadConfig } from "./config.js";

const base = { BETTER_AUTH_SECRET: "x".repeat(32), AUTH_DATABASE_URL: "postgres://a@b/c" };

describe("loadConfig", () => {
  const saved = { ...process.env };
  afterEach(() => {
    process.env = { ...saved };
  });

  it("applies defaults", () => {
    Object.assign(process.env, base);
    const config = loadConfig();
    expect(config.jwtIssuer).toBe(config.baseUrl);
    expect(config.jwtAudience).toBe("brokeros-api");
    expect(config.trustedOrigins).toEqual(["http://localhost:3000"]);
  });

  it("rejects short secrets and dev secrets in production", () => {
    Object.assign(process.env, base, { BETTER_AUTH_SECRET: "short" });
    expect(() => loadConfig()).toThrow(/32 characters/);
    Object.assign(process.env, base, {
      ENVIRONMENT: "production",
      BETTER_AUTH_SECRET: `dev-only-${"x".repeat(32)}`,
    });
    expect(() => loadConfig()).toThrow(/production/);
  });
});
