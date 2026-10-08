# ledger

Double-entry journal for billing (ADR-0012). Other modules call `service.post(...)` with balanced legs and
`service.reverse(...)` to mirror a source's entries.

- **Rules enforced by the database:**
  - a deferred constraint trigger checks at commit that each entry balances per currency;
  - `journal_entries` and `journal_lines` are append-only for `app_user`.
- **Accounts:** `receivable`, `cash`, `client_credit`, `tax_payable`, `revenue`. Every movement between a
  client's money and their invoices passes through `client_credit`.
- `balance(account, client_id=…)` and `trial_balance()` support reports. Integration tests check that
  receivable per client equals the sum of open invoice balances after random sequences of operations.
