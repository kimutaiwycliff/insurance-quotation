# ADR-0009: Billing document states and immutability

- Status: Accepted
- Date: 2026-10-08

## Context
Invoices and credit notes are tax documents. Once issued, KRA (and any auditor) expects them never to change:
corrections are made with a credit note. Payment status changes over time, while the document does not.

## Decision
- One table `billing_documents` holds both `invoice` and `credit_note` (`kind`), with lines in `billing_lines`.
- **`status` is the document's lifecycle:** `draft` → `issued` → `void`.
  - Drafts can be edited freely and have no number.
  - Issuing allocates the number (gapless, ADR-0010), a payment reference for invoices, freezes the lines and
    totals, and posts the ledger journal (ADR-0012).
  - Only an issued invoice with nothing allocated to it can be voided; otherwise issue a credit note.
- **Payment status is derived, never stored:** paid amount = sum of allocations, balance = total − paid. The
  "overdue" state is computed in the tenant's timezone. Statuses are orthogonal: an issued invoice can be
  partly paid and overdue at the same time.
- **Immutability is enforced in the database.** A trigger rejects any change to an issued or void document
  except the void transition (`status`, `voided_at`, `void_reason`), its PDF pointer, and bookkeeping columns.
  It also rejects any change to lines whose document is no longer a draft. `app_user` cannot delete either
  table.
- Credit notes reference the invoice they correct (`credits_document_id`) and are allocated to it. Any excess
  becomes client credit.

## Consequences
- Reports never trust a cached "paid" flag; queries aggregate allocations (indexed by invoice).
- eTIMS (R2.4) attaches its control number at issue time; a transmitted document is corrected only by credit
  note, which this model already requires.
