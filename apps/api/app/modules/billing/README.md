# billing

Invoices, credit notes and payments received (Plan A1.2 R2.1; ADR-0009 states, ADR-0012 ledger).

- **Drafts:** `POST /invoices` and `PATCH /billing-documents/{id}`.
  - Lines come from the item catalogue or are typed in, with quantity, price, discount and a pack tax code.
  - Prices may include VAT.
  - Totals come from `app/calc/invoice.py`: VAT per line, rounded per line.
- **Issue:** `POST /billing-documents/{id}/issue` gives the document its number (gapless), gives an invoice an
  M-Pesa payment reference with a check character, freezes it (database trigger) and posts the journal.
- **Correcting:**
  - `POST /credit-notes` creates a draft against an issued invoice. The total credited per invoice can't exceed
    the invoice. When issued, a credit note is applied to its invoice; any excess becomes client credit.
  - `/void` works on drafts, on invoices with nothing applied, and on credit notes (their applications are
    reversed).
- **Payments:** `POST /payments` records money paid into the tenant's own account; the platform never holds
  funds.
  - It is applied as given, or to open invoices oldest first; anything left is client credit.
  - `POST /invoices/{id}/apply-credit` uses that credit later.
  - `/payments/{id}/void` reverses the payment and everything it paid.
  - `/payments/{id}/receipt` is the numbered receipt PDF.
- **Derived status:** draft, open, partially_paid, paid, overdue (in the tenant's timezone) or void. Paid
  amounts are always summed from allocations.
- **Client account:** `GET /clients/{id}/account` returns what the client owes (ledger receivable), their
  credit on account and their open invoices.
- **Sending:** `POST /billing-documents/{id}/send` creates the PDF and a tracked link (`/d/[token]`), emails
  it, and returns a WhatsApp link.
- **Sales quotes** (`/sales-quotes`, kind `quote`; insurance quotes are a different module):
  - lines can sit under a `section` heading, and `optional` lines are add-ons the client may choose (not in
    the total);
  - sending a draft issues it (number `QT-…`, validity frozen) and creates a link with the `accept` scope;
  - on the link the client accepts (with any add-ons) or declines; the owner is notified;
  - `POST /sales-quotes/{id}/convert` creates a draft invoice from the lines plus the chosen add-ons;
  - status is draft, sent, accepted, declined, expired, invoiced or void.
- **Reminders (daily job, off by default):**
  - covers invoices due within N days, overdue by N days, and quotes expiring within N days;
  - offsets are set per tenant (`invoice_reminder_days_before` / `_after`);
  - each (document, kind, offset) is emailed once (`billing_reminders`), on the reminders stream with
    unsubscribe.
- **Summary:** `GET /billing/summary` returns outstanding, overdue, ageing buckets, this month's invoicing and
  collections, quotes awaiting an answer, and 12 months of invoiced and collected.
- **Permissions:** `invoice:write` for drafts (assistants too), `invoice:issue` to issue, void, credit and
  send, `payment:write` for payments. Reading is scoped like clients (`client:read:own|all`).
