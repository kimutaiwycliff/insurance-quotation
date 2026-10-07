# Security policy

## Reporting a vulnerability
Email **security@<product-domain>** (address to be set once the domain is chosen, decision D7). Do not open public
issues for security problems. We acknowledge within 2 business days and aim to fix critical issues within 7 days.

## Baseline (see docs/SPEC_REVIEW.md §4 and docs/IMPLEMENTATION_PLAN.md)
- Target: OWASP ASVS Level 2.
- Tenant isolation via Postgres Row-Level Security (forced) with composite foreign keys; the API role is not a table owner and has no BYPASSRLS.
- No secrets in the repository. Local defaults in `compose.yaml` are development-only, and production rejects them at startup.
- Logs never contain secrets, tokens or full PII (enforced by a scrubbing processor and tests).
- CI pins every GitHub Action by commit SHA and runs dependency audits (pip-audit) plus image, secret and misconfiguration scans (Trivy).
- The platform never holds or settles client or tenant funds.

## Data protection (Kenya)
- The company registers with the ODPC as a data processor.
- Breach handling targets: the processor notifies the controller within 48 h; the controller notifies the ODPC within 72 h.
- Runbooks live in `docs/runbooks/` (added before R1).
