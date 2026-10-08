# ADR-0013: Jurisdiction pack format & loader

- Status: Accepted
- Date: 2026-10-08

## Context
Levies, stamp duty, tax codes and withholding rates are law, change by Gazette notice, and differ by country.
CLAUDE.md rule 4 says they must be data, never code.

## Decision
- **Packs are versioned YAML files**, `app/jurisdictions/packs/<code>/<version>.yaml`. They are validated at
  load into frozen Pydantic types (`app/calc/pack.py`) and held in memory: they are code-reviewed data
  (CODEOWNERS) and small. Each pack contains:
  - currency, rounding mode and day count;
  - tax codes (VAT, exempt, zero-rated, excise) and which apply to premium, commission and fees;
  - WHT on commission per intermediary type;
  - levy rules (basis, rate, min/max, `charged_to` client|insurer, refundable, commissionable, applicability
    by business line, class and document kind, effective dates, legal source);
  - stamp-duty rules (`flat`, `per_unit_of_sum_insured` with ceil/prorate, `manual`);
  - classes of business with their business line.
- **Sign-off:** `sign_off.status` is `pending` until the tax adviser signs it (D4). Unsigned packs work but
  every calculation, API response (`pack.signed`) and screen says so.
- **Engine** (`app/calc/premium.py`, pure):
  basic premium (rate on sum insured, flat, per member, manual) → minimum premium → benefits →
  loadings and discounts (floored at the minimum) → client-charged levies → one stamp-duty rule → fees and
  fee tax → commission (gross, WHT, VAT and net).
  Each line carries `rule_id@version` and the legal source. Insurer-borne levies are reported, never billed.
- **Tenant pack** = pack for the agency's country (`ke`, else `generic`), latest version. Quotes (R1.3) will
  snapshot the full breakdown, including the pack version, so later pack changes never alter issued
  documents.
- **Golden scenarios** (`tests/golden/ke_premium.yaml`) are hand-calculated with the working shown, run on every
  PR, and change only with a reviewer's approval.

## Consequences
- Unverified items stay manual or flagged rather than guessed:
  - marine and single-journey stamp duty are `manual`;
  - excise on fees is `pending_confirmation`;
  - effective dates are placeholders until sign-off.
- Loading packs into DB tables (as the original plan described) is unnecessary while packs are
  repository data. Revisit if tenants ever need custom rules.
