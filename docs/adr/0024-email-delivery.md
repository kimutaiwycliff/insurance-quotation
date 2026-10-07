# ADR-0024: Email delivery

- Status: Accepted
- Date: 2026-10-07

## Decision
- **Adapter:** `EmailSender` Protocol with SMTP (Mailpit locally; Amazon SES SMTP or Postmark in production)
  and a fake.
- **Identity:** the shared platform address sends as `"<Agency> via <Product>"`, with `Reply-To` set to the
  agency's email. Per-tenant domains with DKIM come in R3.
- **Transactional outbox:** `queue_email()` renders the template, writes `outbound_messages` and defers the
  `messaging.send_email` job **in the business transaction**. The job re-reads the row and only sends
  `queued` messages (idempotent; Procrastinate retries 3 times).
- **Templates per event:** built-ins live in code (`messaging/catalog.py`). Tenants may override subject and
  body per locale (validated by rendering against the event's variables). A broken override falls back to the
  built-in. Rendering is sandboxed with `StrictUndefined`, and subjects are forced onto one line (header
  injection).
- **Streams:**
  - `transactional` (documents a client expects);
  - `reminders` (expiry and renewal nudges), which carry `List-Unsubscribe` and
    `List-Unsubscribe-Post: List-Unsubscribe=One-Click` (RFC 8058) with an HMAC-signed token.
  - Unsubscribes suppress only their stream. Bounces and complaints (from provider webhooks later) suppress
    everything.
- **Opens are not tracked.** "Viewed" means a beacon from a real page render (Apple Mail Privacy Protection
  makes opens meaningless).

## Consequences
SMTP runs in a worker thread inside jobs, never in request handlers. SES bounce and complaint webhooks are a
follow-up (they need the webhook ingress, ADR-0016).
