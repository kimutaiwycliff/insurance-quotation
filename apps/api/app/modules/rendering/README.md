# rendering

Document templates, tenant branding, previews and generated PDFs (ADR-0014; authoring guide `docs/templates.md`).

- **Endpoints:** `GET /templates`, `POST /templates/{key}/preview` (pdf or html; unsaved branding overrides),
  `GET/PATCH /branding` (If-Match).
- **Service API:** `generate_pdf(session, storage, renderer, tenant_id=, view=, entity=, actor=)` → cached Document.
- **Permissions:** `org:read` (catalogue, preview, branding read), `branding:manage`.
