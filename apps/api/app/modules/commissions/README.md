# commissions

Commission tracking for agents (Plan A1.1 R1.5): **expected vs received**, with the WHT insurers withhold.

- **Expected** commission is stored on each policy (`policies.commission`). It comes from:
  - the quote's calculation;
  - a product's rate and the "premium before levies" entered on a policy;
  - `PUT /policies/{id}/commission {rate, base}`.
- The arithmetic is `app/calc/commission.py` (pure):
  - gross = base × rate;
  - WHT = gross × the pack's rate for the agency's intermediary type (KE: 10% for resident agents, 5% for
    brokers);
  - net = gross − WHT + VAT (commission VAT is exempt in KE).
- **Received** commission is recorded as a receipt:
  - `POST /commission-receipts`: insurer, date, reference, KRA WHT certificate number, and one line per policy
    with the gross paid (WHT defaults to the pack rate; enter the insurer's figure to override it);
  - receipts are voided (`/void`), never edited or deleted; allocations are append-only.
- **Reading:**
  - `GET /commissions/statement` (per policy: expected, received, outstanding; `?outstanding=true`,
    `?insurer=`, `?policy_id=`);
  - `GET /commissions/summary?year=` (by month and insurer, plus WHT certificates);
  - `GET /commission-receipts`.
- **Permissions:**
  - `commission:read:own` sees figures for the member's own policies only (from allocations);
  - `commission:read:all` also sees whole receipts and the WHT certificates list;
  - `commission:manage` (owners, admins, accounts) records and voids receipts and sets expected commission.
- Splits between agents in an agency (sub-agents) are out of scope for R1 (Plan A1: broker-only for now).
