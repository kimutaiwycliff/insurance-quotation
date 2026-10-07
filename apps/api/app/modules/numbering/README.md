# numbering

Document number schemes and gapless allocation (ADR-0010), plus M-Pesa payment references.

- **Entities:** `NumberingScheme` (document type, optional branch, pattern, reset period, start value),
  `NumberSequence` (last value per scheme and period).
- **Service API (for other modules):** `allocate_number(session, tenant_id, document_type, on=..., branch_id=...,
  branch_code=...)`. Call it inside the transaction that issues the document. `seed_default_schemes()`.
- **Pure helpers:** `pattern.py` (parse and format patterns), `references.py` (`generate_payment_reference`,
  `is_valid_payment_reference`).
- **Endpoints:** `GET/POST /numbering-schemes`, `PATCH /numbering-schemes/{id}` (If-Match),
  `POST /numbering-schemes/preview`.
- **Permissions:** `numbering:read`, `numbering:manage`.
