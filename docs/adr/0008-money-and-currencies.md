# ADR-0008: Money, currencies & rounding

- Status: Accepted
- Date: 2026-10-07

## Decision
- Amounts are `Decimal` (`app/core/money.py: Money`), stored as `NUMERIC(20,4)` and sent in JSON as
  `{"amount": "1234.50", "currency": "KES"}`. Floats are rejected at the boundary.
- Arithmetic keeps 4 decimal places. Rounding to the ISO 4217 minor unit (KES 2, UGX 0, KWD 3) happens only in
  `Money.rounded()`, with `ROUND_HALF_UP` by default. The rounding mode is a parameter because jurisdiction
  packs may require another.
- Supported currencies are listed in `ISO_4217_MINOR_UNITS`. The global `currencies` table is seeded from the
  same list, and an integration test keeps the two equal.
- Operations across currencies raise; conversion (FX) is out of scope until a module needs it.
