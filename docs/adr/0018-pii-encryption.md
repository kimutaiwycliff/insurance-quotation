# ADR-0018: PII encryption & key management

- Status: Accepted
- Date: 2026-10-08

## Context
Agents keep clients' national ID and passport numbers. Under the Kenya Data Protection Act 2019, these are
sensitive personal data. Database-level encryption at rest protects disks, not a leaked backup or a SQL
injection.

## Decision
- **Application-level AES-256-GCM** for ID and passport numbers (`app/core/crypto.py`):
  - the ciphertext format is `<key_id>:<base64(nonce|ciphertext|tag)>`, with the key id as associated data;
  - keys come from `PII_ENCRYPTION_KEYS` (`key_id:base64(32 bytes)`, comma-separated): the first one encrypts
    and all of them decrypt, so a key can be rotated without downtime.
- **Lookup and duplicate detection** use a keyed HMAC-SHA256 (`PII_LOOKUP_KEY`) of the normalised value (no
  spaces, dashes or case). Search by ID number works without decrypting anything.
- Responses carry only a masked hint (`•••••678`). The full number is returned only by
  `POST /clients/{id}/id-number`, which writes `client.id_number_viewed` to the audit log.
- Development keys are refused in production. In production, keys live in the secrets manager (a KMS-wrapped
  data key when hosting is decided, D6).

## Consequences
- Rotating the lookup key requires re-hashing every row (a one-off job). Rotating encryption keys does not:
  add the new key first in the list, then re-encrypt in the background if you want to retire the old one.
- Other sensitive fields (medical details for members, R1.3+) use the same helpers.
