/** HTTP app: Better Auth under /api/auth/*, plus liveness/readiness probes. */
import { Hono } from "hono";
import type { Pool } from "pg";

import type { Auth } from "./auth.js";

export function createApp(auth: Auth, pool: Pool) {
  const app = new Hono();

  app.get("/health/live", (c) => c.json({ status: "ok" }));
  app.get("/health/ready", async (c) => {
    try {
      await pool.query("SELECT 1");
      return c.json({ status: "ok" });
    } catch {
      return c.json({ status: "fail" }, 503);
    }
  });

  app.on(["GET", "POST"], "/api/auth/*", (c) => auth.handler(c.req.raw));
  return app;
}
