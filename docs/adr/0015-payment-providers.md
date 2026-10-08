# ADR-0015: Payment providers: M-Pesa Daraja first, cards later

- Status: Accepted
- Date: 2026-10-08
- Supersedes: the "Paystack first" recommendation in ADR-0001 and plan §6 M4

## Context
The product owner decided (2026-10-08) to launch with **M-Pesa only**. Nearly every Kenyan client and agent
pays by M-Pesa, and the Daraja API needs no third-party gateway account. Paystack (cards) is on hold; the UI
shows cards as "coming soon". The platform must never hold or settle client or tenant funds (CLAUDE.md
rule 5).

## Decision
- **One provider at launch: `mpesa_daraja`.** Each tenant connects **its own** Paybill or Till (shortcode,
  passkey, consumer key and secret), stored encrypted (ADR-0018 keys). Money goes straight from the client
  to the tenant's shortcode; we only orchestrate and record.
- **Collection:**
  - **STK Push** from the public invoice page and from the app ("send payment prompt"), with the invoice's
    payment reference as `AccountReference`;
  - **C2B** confirmations for clients who pay the Paybill manually, matched on the account reference.
    Anything that does not match lands in an **unmatched payments** queue for the tenant to allocate.
- **Trust nothing from callbacks:** callbacks arrive on an unguessable per-connection path. A successful STK
  callback is confirmed with the **STK Query** API before a payment is recorded. Receipts are idempotent on
  the M-Pesa receipt number, and an optional Safaricom IP allow-list is applied.
- **Behind an interface:** a `PaymentProvider` protocol has `daraja`, `fake` (tests, local) and later
  `paystack`. Cards are shown as "coming soon"; adding Paystack later is an adapter plus a connection type.
- **Our own subscriptions** (D8) are collected the same way, on the platform's own Daraja shortcode.

## Consequences
- The sandbox needs Daraja test credentials (consumer key and secret; the sandbox shortcode and passkey are
  public). CI uses the fake provider; sandbox tests are marked and skipped without credentials.
- Tenants must have a Paybill or Till and a Daraja app. Onboarding includes a guided go-live checklist.
