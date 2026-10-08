# clients

The agency's book: individual and corporate clients, households, corporate contacts and the activity log.

- **Scoping:** `client:read:all` sees every client; `client:read:own` sees only clients the member owns. Other
  agents' clients return 404.
- **Endpoints:**
  - `GET/POST /clients` (search `q`: name, phone in any format, email, KRA PIN, ID number);
  - `POST /clients/duplicates`;
  - `GET/PATCH /clients/{id}` (If-Match, `archived`);
  - `POST /clients/{id}/id-number` (audited reveal);
  - `GET /clients/{id}/timeline`;
  - activities and contacts;
  - `GET/POST/PATCH /households`.
- **PII:** ID numbers encrypted (ADR-0018); phones stored in E.164 (`app/core/phone.py`).
- **Duplicates:** creating a client with a known phone, email, PIN or ID returns 409 `possible_duplicate` unless
  `allow_duplicate`. Matches in another agent's book are counted (`hidden`), never shown.
- **Audit:** `client.created`, `client.updated`, `client.id_number_viewed`, `household.created`.
