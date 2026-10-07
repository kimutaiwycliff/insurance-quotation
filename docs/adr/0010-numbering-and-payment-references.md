# ADR-0010: Document numbering & payment references

- Status: Accepted
- Date: 2026-10-07

## Decision
1. **Schemes** (`numbering_schemes`) per document type, optionally per branch, with a pattern such as
   `INV-{YYYY}-{SEQ:5}` (tokens `{YYYY} {YY} {MM} {BRANCH} {SEQ[:n]}`; literals limited to `A-Z a-z 0-9 - / _ .`;
   at most 40 characters formatted) and a reset period: `never`, `yearly` or `monthly`. New tenants get generic
   defaults for quote, invoice, receipt and credit note. These are not jurisdictional, because KRA eTIMS assigns
   its own control numbers.
2. **Gapless allocation at issue time.** `allocate_number()` increments `number_sequences(tenant, scheme, period)`
   with `INSERT ... ON CONFLICT DO UPDATE ... RETURNING` inside the issuing transaction. The row lock
   serialises concurrent issuers. A rolled-back issue rolls back its increment, so there are no gaps. Drafts
   never consume numbers. The period and date tokens use the issue date in the tenant's timezone.
3. A branch scheme takes precedence over the tenant-wide scheme.
4. **Payment references** for M-Pesa STK/C2B (AccountReference ≤ 12 characters) are 9 random characters plus a
   check character. The alphabet has no look-alikes (31 characters). The check is a weighted sum mod 31, which
   detects every single-character error and every adjacent swap. Luhn mod N was rejected because it needs an
   even alphabet size. The formal document number stays separate.

## Consequences
- Verified by a 50-way concurrent allocation test (gapless and unique), a rollback test and property tests.
- Allocation serialises issues of one scheme within a tenant. That is acceptable at agency volumes; revisit if
  a tenant issues more than ~50 documents per second.
