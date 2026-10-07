# ADR-0023: Documents & uploads

- Status: Accepted
- Date: 2026-10-07

## Decision
- Files go straight from the browser or phone to object storage via a **presigned PUT** (default 10 min). The
  URL signs the exact `Content-Type` and `Content-Length`, so other sizes or types are refused by storage itself.
- `.../complete` streams the object once and checks four things: the size matches the announcement; the
  magic bytes match the extension (allow-list: pdf, png, jpg, webp, heic, docx, xlsx, csv); the type is
  recorded from the bytes, not the client's claim; and the SHA-256 hash is stored. Rejected bytes are deleted
  immediately.
- Documents have **versions** (new upload = new version; the current version is the latest ready one), **links**
  to any entity (`entity_type`, `entity_id`), an optional `expires_on` (KYC reminders) and are archived, never
  deleted.
- Storage keys contain no user text (`t/<tenant>/d/<doc>/v<n>/<random>`). Downloads are presigned GETs
  (default 5 min) issued after the permission check, with the original filename in `Content-Disposition`.
- Presigning uses `S3_PUBLIC_ENDPOINT_URL` (browser-reachable); server I/O uses the internal endpoint.
- Server-generated files (PDFs) use `store_bytes()` with an optional `source_key` for caching.

## Consequences
- A pending version whose upload never completes stays pending. A cleanup job for stale pending versions and
  orphan objects comes with M2 hardening.
- Malware scanning (ClamAV) can hook into `complete_upload` later (spec P2).
