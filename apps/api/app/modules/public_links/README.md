# public_links

Tracked, revocable links to documents (and later quotes, invoices, receipts) (ADR-0014).

- **Tenant:** `POST /public-links` (optional `send_to` emails it), `GET /public-links`,
  `POST /public-links/{id}/revoke`, `GET /public-links/{id}/events`.
- **Anonymous** (`/api/v1/public/links/{token}`): `GET` (summary), `/html` (sandboxed web view), `/download`
  (302 to a presigned GET), `POST /beacon` (counts a view; bots excluded). Rate limited per IP.
- **Extending:** `service.register_target(entity_type, resolver)` returns `PublicContent(title, kind, html, download)`.
- **Events:** created, sent, opened, viewed, downloaded, revoked. The first human view notifies the sender.
- **Permissions:** `link:manage` (create, revoke), `document:read` (list, events).
