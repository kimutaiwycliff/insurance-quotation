# Architecture Decision Records

Format: Context / Decision / Consequences. Status is one of Proposed, Accepted, Superseded by NNNN.
Write the ADR when the milestone that needs it starts (backlog in `docs/IMPLEMENTATION_PLAN.md` §3.3).

| # | Title | Status | Date |
|---|---|---|---|
| [0001](0001-technology-stack.md) | Technology stack | Accepted | 2026-10-07 |
| [0002](0002-release-sequencing-agent-first.md) | Release sequencing: agent-first, backend-first per slice | Accepted | 2026-10-07 |
| [0003](0003-tenancy-and-rls.md) | Tenancy & Row-Level Security model | Accepted | 2026-10-07 |
| [0004](0004-job-runner-procrastinate.md) | Job runner: Procrastinate on Postgres | Accepted | 2026-10-07 |
| [0005](0005-object-storage.md) | Object storage: S3 API, RustFS for dev/CI | Accepted | 2026-10-07 |
| [0006](0006-auth-topology.md) | Authentication topology & JWT flow | Accepted | 2026-10-07 |
| [0007](0007-roles-and-permissions.md) | Roles & permissions (agent-first) | Accepted | 2026-10-07 |
| [0008](0008-money-and-currencies.md) | Money, currencies & rounding | Accepted | 2026-10-07 |
| [0009](0009-billing-document-states.md) | Billing document states & immutability | Accepted | 2026-10-08 |
| [0010](0010-numbering-and-payment-references.md) | Document numbering & payment references | Accepted | 2026-10-07 |
| [0011](0011-idempotency-and-concurrency.md) | Idempotency keys & optimistic concurrency | Accepted | 2026-10-07 |
| [0012](0012-ledger.md) | Double-entry ledger for billing | Accepted | 2026-10-08 |
| [0013](0013-jurisdiction-packs.md) | Jurisdiction pack format & loader | Accepted | 2026-10-08 |
| [0014](0014-template-rendering-and-public-pages.md) | Template rendering & public-page isolation | Accepted | 2026-10-07 |
| [0018](0018-pii-encryption.md) | PII encryption & key management | Accepted | 2026-10-08 |
| [0019](0019-premium-collection-and-activation.md) | Premium collection modes & activation gating | Accepted | 2026-10-08 |
| [0021](0021-frontend-bff-and-data-fetching.md) | Frontend data fetching & BFF | Accepted | 2026-10-07 |
| [0022](0022-api-client-codegen.md) | API client code generation | Accepted | 2026-10-07 |
| [0023](0023-documents-and-uploads.md) | Documents & uploads | Accepted | 2026-10-07 |
| [0024](0024-email-delivery.md) | Email delivery | Accepted | 2026-10-07 |
