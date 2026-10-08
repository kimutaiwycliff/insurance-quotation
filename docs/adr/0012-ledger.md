# ADR-0012: Double-entry ledger for billing

- Status: Accepted
- Date: 2026-10-08

## Context
Tenants need balances that reconcile: what clients owe, the client credit they hold, tax charged. Summing
documents ad hoc drifts as soon as voids, credit notes and partial payments mix. The ledger is the tenant's own
books of record. The platform never holds money (CLAUDE.md rule 5); payments are records of what the tenant
received in its own accounts.

## Decision
- Tables `journal_entries` (source type and id, date, memo) and `journal_lines` (account, debit, credit,
  currency, client).
- **Balance is enforced in the database:** a deferred constraint trigger checks at commit that each entry's
  debits equal its credits per currency. Both tables are append-only for `app_user`. Mistakes are reversed by
  a new entry.
- **Chart of accounts v1** (codes are fixed; a tenant chart comes later):

  | Code | Account | Type |
  |---|---|---|
  | `receivable` | Amounts clients owe | asset |
  | `cash` | Money received (bank, M-Pesa, cash) | asset |
  | `client_credit` | Money received or credited but not yet applied to an invoice | liability |
  | `tax_payable` | VAT charged on invoices | liability |
  | `revenue` | Sales | income |

- **Postings:** every movement between a client's money and their invoices goes through `client_credit`, so
  "allocated" and "unallocated" stay consistent.

  | Event | Debit | Credit |
  |---|---|---|
  | Invoice issued | receivable (total) | revenue (net), tax_payable (tax) |
  | Credit note issued | revenue (net), tax_payable (tax) | client_credit (total) |
  | Payment recorded | cash | client_credit |
  | Allocation (payment or credit note to invoice) | client_credit | receivable |
  | Invoice voided | reversal of its issue entry | |
  | Payment voided | reversal of its allocations, then client_credit | cash |

## Consequences
- Receivable per client always equals the sum of open invoice balances. An integration test checks this
  after random sequences of operations.
- Refunds of client credit (R2.3, linked to a credit note) post client_credit → cash.
