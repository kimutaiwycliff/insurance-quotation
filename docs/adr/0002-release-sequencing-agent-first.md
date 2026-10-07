# ADR-0002: Release sequencing — agent-first, backend-first per slice

- Status: Accepted (product owner, 2026-10-07)
- Supersedes: `docs/PROJECT_SPEC.md` §0.2.1 ("no frontend until backend B0–B8") and the broker-first P1 scope

## Context
- The spec built ~20 modules and 8 backend milestones before any UI, which meant months without user feedback or revenue.
- Research found only 181 licensed broker firms in Kenya and a self-serve competitor (InsurOps) already targeting them.
- The product owner confirmed the insurance tier targets **Kenyan insurance agents** who want to manage clients well
  and win more business.

## Decision
1. **R0 Foundations** (M0–M2, W1), then **R1 Agent MVP**:
   - client CRM;
   - leads pipeline;
   - insurers and products;
   - insurance quotes with Kenyan levy calculation;
   - policy book (client pays the insurer directly by default);
   - renewals and reminders;
   - commission tracking (10% WHT);
   - document vault;
   - import of the existing book.
2. **R2**: Invoicing tier, online payments (Paystack, M‑Pesa) and eTIMS. **R3**: growth & automation (portal, WhatsApp API, AI extraction, mobile).
3. Backend-first **per slice**: each slice's API is complete and tested in Compose (with `openapi.json` committed) before its UI starts.
4. Broker-only features are deferred (premium trust accounts, remittance batches, INS 153‑1 returns, statement reconciliation, sub-agent hierarchies). The data model keeps `collection_mode` so they can be added later.

## Consequences
- Web work starts after M1 and runs one milestone behind the backend.
- Pilot agents give feedback from R1. Release gates in the plan apply at each release.
- Open legal question: may a Kenyan agent hold several insurer appointments per class? It decides how multi-insurer comparison is framed (D5).
