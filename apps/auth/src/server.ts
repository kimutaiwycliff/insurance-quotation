import { serve } from "@hono/node-server";

import { createApp } from "./app.js";
import { createAuth } from "./auth.js";
import { loadConfig } from "./config.js";

const config = loadConfig();
const { auth, pool } = createAuth(config);
const app = createApp(auth, pool);

const server = serve({ fetch: app.fetch, port: config.port, hostname: "0.0.0.0" }, (info) => {
  console.log(JSON.stringify({ level: "info", event: "startup", port: info.port }));
});

for (const signal of ["SIGINT", "SIGTERM"] as const) {
  process.on(signal, () => {
    server.close(() => {
      void pool.end().then(() => process.exit(0));
    });
  });
}
