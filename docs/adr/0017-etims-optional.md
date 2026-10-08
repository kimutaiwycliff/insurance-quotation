# ADR-0017: eTIMS is optional at launch

- Status: Accepted
- Date: 2026-10-08

## Context
Kenyan law expects eTIMS invoices from businesses (SPEC_REVIEW §2), but integrating with KRA (OSCU/VSCU
certification, device initialisation, sandbox access) is slow and uncertain. The product owner decided
(2026-10-08) that **eTIMS is optional for now**, so the product can launch without it.

## Decision
- **A tenant setting, off by default.** When a tenant turns eTIMS on, issued invoices and credit notes get
  an **eTIMS reference** step: the tenant records the KRA control (CU) invoice number and the QR or
  verification URL issued by their own eTIMS tool, and we print them on the PDF (`tax_control`).
- No KRA integration ships at launch. The `kra_etims_oscu` adapter stays planned behind the same tax adapter
  interface, so certified integration can replace the manual step later without changing documents.
- When eTIMS is off, documents show no eTIMS fields, and the tenant is responsible for compliance through
  their own tools. The settings page states this plainly.

## Consequences
- Lower launch risk and no dependency on KRA certification.
- Reports and exports include the eTIMS reference when it was recorded, ready for an accountant.
