# ADR-0019: Premium collection modes & activation gating

- Status: Accepted
- Date: 2026-10-08

## Context
Kenyan agents (the R1 customer, Plan A1) mostly have clients pay the insurer directly. Some insurers authorise
agents to collect premium; those agents must remit it "immediately upon receipt" (Insurance Regulations r.42).
Insurance Act s.156(1) forbids an insurer to assume a general-insurance risk before the premium is received
("no premium, no cover"). Regs r.43 lists the exceptions: medical instalments, declaration policies, provisional
premiums, marine (15 days), staggered bonds and contractor's all risks. The 2019 amendment, which barred
intermediaries from receiving premium, was nullified in 2021. Whether the decision was appealed is unverified
(D5), so the rules must be able to change without a migration. The platform never holds or moves funds
(CLAUDE.md rule 5).

## Decision
- Each policy carries a **`collection_mode`**: `insurer_direct` (the default) or `agent_collected`. A
  `broker_collects` mode (trust account, remittance batches) can be added later; it is a new value, not a schema
  change.
- **Payments are records, not money movement.** `policy_payments` stores the amount, date, method, reference and
  who was paid (`insurer` or `agent`). Rows are never deleted or edited: a wrong entry is voided with a reason
  and entered again. The only later change allowed is marking an agent-collected payment as remitted.
- **Remittance alert:** recording a payment received by the agent opens a high-priority task for the policy
  owner, due at 17:00 the same day: "Remit KES … to <insurer>". Marking the payment as remitted closes the task.
  The dashboard counts unremitted payments.
- **Activation gate:** a policy starts as `pending` and becomes `active` only when the insurer has confirmed
  cover and one of these holds:
  - non-voided payments cover the total premium;
  - an exception from the jurisdiction pack's `premium_exceptions` applies to the policy's class on that date.
  The activation evidence (basis, exception id and legal source, pack version, amount paid, who activated it)
  is stored on the policy and in the audit log.
- The **exceptions are pack data** (`premium_exceptions` in `ke/2026.1`, pending sign-off D4/D5), never code.
  The generic pack has none.

## Consequences
- An agent cannot mark unpaid motor cover as active. If an insurer grants credit outside r.43, the agent records
  a payment once it is made. This is deliberate.
- Reports of premium "collected vs outstanding" (R1.5 dashboard v2) read `policy_payments`. Commission
  received is a separate ledger (R1.5).
- If the law changes, update the pack (and possibly the default collection mode). No migration is needed.
