# Runbook: PDF rendering backlog or failures

Symptoms: previews or sends fail with 500 `internal_error`, and the logs show `PdfRenderError`; or the
`pdf`/`messaging` queues grow.

1. `docker compose ps gotenberg` (or the service health in production). Gotenberg exposes `/health`.
2. Gotenberg logs (JSON): Chromium crashes, timeouts (`--api-timeout=30s`) or memory pressure. Scale Gotenberg
   horizontally; it is stateless.
3. A single document failing every time usually means huge content (thousands of lines) or a bad logo. Check
   the logo size (≤ 1 MB enforced) and the line count, then re-render.
4. Stuck jobs: `make jobs-shell` → `list_jobs --status failed` → `retry <id>` after the cause is fixed.
5. Never relax the hardening flags (`--chromium-deny-private-ips`, `--chromium-allow-list`,
   `--chromium-disable-javascript`) to "fix" a render. Templates must be self-contained.
