# ADR-0014: Template rendering & public-page isolation

- Status: Accepted
- Date: 2026-10-07

## Context
Quotes, invoices and receipts are the product's shop window: agents send them as branded PDFs and tracked
links. Tenant-entered text (names, notes) flows into HTML, and the PDF renderer is a headless browser. That
creates XSS and SSRF risks (SPEC_REVIEW §4.5).

## Decision
1. **One template, two outputs.** Templates are HTML/CSS Jinja2 files in `app/modules/rendering/templates/<key>/`
   (`manifest.json` + `document.html.j2`, sharing `_base.html.j2` and `_blocks.html.j2`). The same HTML is the
   PDF source and the public web view.
2. **Templates see a view model only** (`rendering/view.py: DocumentView`, `BrandingView`), never the database.
   Modules build the view; amounts are computed upstream (app/calc), and templates only format them through
   `Money.rounded()`.
3. **Safe by construction:**
   - `ImmutableSandboxedEnvironment` with `autoescape=True` and `StrictUndefined`;
   - no tenant-authored templates;
   - `| safe` is used only for our own generated font CSS;
   - colours and logo data URIs are validated by pattern;
   - text colour on brand colours is chosen for WCAG contrast.
4. **Self-contained HTML.**
   - Fonts (Inter, Source Serif 4, OFL) and the logo are inlined as `data:` URIs.
   - Every page carries the CSP `default-src 'none'; style-src 'unsafe-inline'; img-src data:; font-src data:`.
   - Gotenberg runs with JavaScript off, private IPs denied and an allow-list of `file:///tmp/` only.
   - Tests prove that even HTML without our CSP cannot reach a canary on the private network or the metadata IP.
5. **Public pages.**
   - The HTML is served by `/api/v1/public/links/{token}/html` with the CSP above, `frame-ancestors` limited to
     the web origin, `no-store`, `noindex` and `no-referrer`.
   - The web app shows it in a sandboxed iframe without `allow-scripts`.
   - Views count only when the page sends a beacon; link-preview bots (WhatsApp, Facebook...) are recorded,
     not counted.
6. **Public links.**
   - Tokens are 32 random bytes, stored as SHA-256.
   - Anonymous requests resolve the token with a narrow `SECURITY DEFINER` function, then run under RLS.
   - Expired or revoked links return 410; revocation applies immediately.
   - Rate limits are per client IP.
   - What a link shows is a *target* registered per entity type. M2 ships `document`; quotes and invoices add
     theirs.
7. **Caching.** Generated PDFs are stored as documents keyed by SHA-256 of (template, template version,
   branding, view). Unchanged documents are never re-rendered.
8. **Launch set (plan M2):** `classic` (free), `savanna` and `executive` (premium). The spec's eight templates
   follow with the template marketplace. Tier gating (`require_feature`) arrives with SaaS billing.

## Consequences
- A template change needs a `version` bump in its manifest (this invalidates the PDF cache) and passes the
  fixture-set tests (standard, long names, 150 lines, zero-decimal currency, RTL).
- The Latin font subsets don't cover Arabic, so RTL text falls back to Gotenberg's Noto fonts.
- Visual-diff snapshot testing is deferred: it needs PDF rasterisation tooling, which is an ADR-0001 addition.
