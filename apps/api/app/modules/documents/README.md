# documents

Files with versions, entity links and expiry dates (ADR-0023).

- **Flow:** `POST /documents` (presigned PUT) → upload → `POST /documents/{id}/versions/{n}/complete`
  (size, magic bytes, SHA-256) → `GET /documents/{id}/download` (presigned GET, 5 min).
- **Also:** `GET /documents` (filters: entity, category, `expiring_before`), `GET/PATCH /documents/{id}`
  (If-Match; `archived`), `POST /documents/{id}/versions`, `POST/DELETE /documents/{id}/links`.
- **Service API:** `store_bytes`, `find_by_source_key`, `read_current`, `download_url`, `get_document`.
- **Permissions:** `document:read`, `document:write`.
