# Template authoring guide

Templates live in `apps/api/app/modules/rendering/templates/<key>/` (see ADR-0014).

1. Copy `classic/` to a new folder. The folder name **is** the key and must match `manifest.json` → `key`.
2. In `manifest.json` set `name`, `description`, `tier` (`free`/`premium`), `doc_types`, `font_pair`
   (`sans`/`serif`), default colours and `version` (bump it on every visual change: it invalidates cached PDFs).
3. Write `document.html.j2`: `{% extends "_base.html.j2" %}`, put CSS in `{% block style %}` and markup in
   `{% block body %}`. Reuse the macros from `_blocks.html.j2` (party, meta, details, lines, totals, payment,
   closing): they carry accessibility markup (table captions, `scope`, `dir="auto"`) and page-break rules.
4. Available data: `doc` (`DocumentView`), `brand` (`BrandingView`), `title`, `on_primary` (text colour that
   contrasts with the brand colour). CSS variables: `--primary --accent --on-primary --ink --muted --rule --wash`.
5. Rules:
   - no external URLs, ever (the CSP blocks them anyway);
   - no `| safe` on data;
   - money only through the `money` filter, dates through `date`;
   - print sizes in `pt`/`mm`.
6. Run `uv run pytest tests/unit/test_m2_pure.py` (every doc type and fixture set renders) and
   `make test` (real PDFs through Gotenberg, with text assertions). Preview it in the app:
   `POST /api/v1/templates/<key>/preview` with `{"format": "html"}` or `"pdf"`.
