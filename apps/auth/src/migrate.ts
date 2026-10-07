/**
 * Creates/updates Better Auth tables in the `auth` schema (runs as auth_owner, one-shot Compose service).
 * Refuses unsafe changes (e.g. adding a required column to a non-empty table): fix those with a manual
 * migration and a runbook entry.
 */
import { getMigrations } from "better-auth/db/migration";

import { createAuth } from "./auth.js";
import { loadConfig } from "./config.js";

const config = loadConfig();
const { auth, pool } = createAuth(config);
try {
  const { toBeCreated, toBeAdded, runMigrations } = await getMigrations(auth.options, {
    throwOnUnsafe: true,
  });
  console.log(
    JSON.stringify({
      event: "auth_migrations",
      create: toBeCreated.map((t) => t.table),
      alter: toBeAdded.map((t) => t.table),
    }),
  );
  await runMigrations();
} finally {
  await pool.end();
}
