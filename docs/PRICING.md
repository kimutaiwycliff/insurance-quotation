# Pricing proposal (decision D8)

Status: **approved by the product owner on 2026-10-08**; **changed on 2026-10-19 to trial-only** (no free plan,
14-day trial, founding discount on monthly payments only; see "Trial-only since 2026-10-19" below).
Researched 2026-10-08. Prices are monthly, in KES, paid by
M-Pesa, VAT-inclusive.

## What the market looks like

| Who | What they pay today | Source |
|---|---|---|
| Kenyan SME invoicing | Zoho Books KES 999 / 1,999 / 2,999; Risiti (eTIMS invoicing) KES 1,000; Veira KES 2,999 / 5,999 / 9,999 | [mocky.co.ke](https://mocky.co.ke/blog/accounting-software-kenya-etims-ready-options-costs-and-setup-for-smes-in-2026), [veirahq.com](https://veirahq.com/blog/best-invoicing-software-kenya/) |
| Insurance CRMs abroad | Specialist systems: AgencyBloc USD 109 per user (≈ KES 14,000); Applied Epic USD 125–250 per user. Lighter tools: NowCerts USD 59, InsuredMine USD 44. Generic CRM (Zoho) USD 14–52 per user | [enrollhere.com](https://enrollhere.com/blogs/insurance-agency-software-pricing), [unlockedcrm.ai](https://unlockedcrm.ai/blog/insurance-crm-pricing-breakdown-2026), [crm.org](https://crm.org/crmland/best-insurance-crm) |
| Kenyan insurance software | Broker and insurer systems (Rensoft, TurnQuest, InsurOPS): quote-based, aimed at firms, not individual agents. No affordable agent product with public prices was found | [rensoft.co.ke](https://rensoft.co.ke/), [rediansoftware.com](https://www.rediansoftware.com/insurance-claims-management-software-kenya-implementation-guide) |

**Who the customers are:**
- **Market size:** IRA counted about **15,000 licensed agents** in 2024, up from 14,648 in 2023
  ([IRA licensed agents](https://www.ira.go.ke/licensed-insurance-agents/)).
- **Commission:** agents earn **10–25%** of premium.
- **Income:** typically **KES 20,000–40,000 a month** starting out, and **KES 60,000–150,000+** once
  established ([bimasasa.co.ke](https://bimasasa.co.ke/blog/how-to-become-insurance-agent-kenya),
  [Glassdoor](https://www.glassdoor.com/Salaries/nairobi-insurance-agent-salary-SRCH_IL.0,7_IM1085_KO8,23.htm)).

**What this means:**
1. **There is a gap.** Foreign insurance CRMs cost KES 6,000–30,000 per user and know nothing about Kenyan
   levies, M-Pesa or IRA rules. Local systems sell to brokers and insurers. Nobody serves the individual
   agent at a price they can pay.
2. **The SME invoicing price is set.** Kenyan small businesses expect about **KES 1,000 a month**.
3. **One saved renewal pays for a month.** A typical motor renewal of KES 30,000 earns the agent about
   KES 3,000. We sell "never miss a renewal again" for less than one renewal's commission.

## Recommended plans

| | **Agent** | **Agency** | **Business** |
|---|---|---|---|
| For | One working agent | Agencies with a team | SMEs: quotes and invoices only |
| Price | **KES 1,500/mo** | **KES 4,500/mo**, 5 users included, then KES 700 per extra user | **KES 999/mo**, 3 users |
| Yearly (2 months free) | KES 15,000 | KES 45,000 | KES 9,990 |
| Clients | Unlimited | Unlimited | Unlimited |
| Insurance quotes, policies, renewals board | ✓ | ✓ | — |
| Renewal reminders to clients (email, WhatsApp link) | ✓ | ✓ | — |
| Multi-insurer comparison quotes, commission tracking, import of the book | ✓ | ✓ | — |
| Invoices, sales quotes, receipts, M-Pesa payments | ✓ | ✓ | ✓ |
| Own logo and colours | ✓ | ✓, all templates | ✓ |
| Team roles, agents see only their own clients | — | ✓ | ✓ |
| eTIMS (manual reference now, integration later) | ✓ | ✓ | ✓ |
| Support | WhatsApp | WhatsApp with priority, onboarding call | WhatsApp |

**Why these numbers:**
- **Agent, KES 1,500:**
  - It's about 1–2.5% of an established agent's monthly income, and half one renewal's commission.
  - It's priced above SME invoicing (it does far more) but at a tenth of the foreign insurance CRMs.
  - Under KES 2,000 is a "just pay it on M-Pesa" decision, with no committee.
- **Agency, KES 4,500 for 5:** works out to KES 900 per seat, so growing agencies are rewarded. Team
  features (roles, own-client scoping, a dashboard per agent) are what principals pay for.
- **Business, KES 999:** matches the Kenyan reference price (Zoho Standard, Risiti). It wins on M-Pesa
  collection, tracked links and reminders rather than on price.
- **No free plan, a 14-day trial (decided 2026-10-19, replacing the Free plan and 30-day trial):**
  - New sign-ups get 14 days of **Agency** (everything, including the team) with no card. After that the
    account is **read-only** until they pay: everything can still be seen and downloaded, nothing is deleted,
    and paying unlocks it straight away.
  - Why: freemium converts about 3–4% of free users, opt-in trials about 14–25%, and trials pay off in weeks
    rather than months ([Dodo Payments](https://dodopayments.com/blogs/saas-free-trial-vs-freemium),
    [Fungies](https://fungies.io/saas-free-trial-vs-freemium-2026)). A 50-client free plan covered a new
    agent's whole book, and 10 free invoices a month covered many small businesses, so neither had a reason
    to pay. A free plan also brings support load with no revenue.
  - What we give up: the word-of-mouth of free users. The trial, the founding offer and referrals carry that.
  - Agencies on the old Free plan whose trial had ended got a fresh 14-day trial when this changed.

## Launch offers (first 6 months)

- **Founding members:** the first 100 paying agents get 50% off for 12 months: Agent at KES 750, Agency at
  KES 2,250. **Monthly payments only:** it does not stack with the yearly saving (2 months free). This creates urgency, early references and testimonials.
- **Referrals:** one month free for both sides when a referred agent pays for their first month. Agents sit
  in WhatsApp groups per insurer and per town, which is exactly where referrals spread.
- **Insurer and agency partnerships:** a principal agency or an insurer's agency team buys 20+ seats at
  KES 600 per seat. It's the fastest way to reach volume.

## How customers pay

- **M-Pesa only at launch** (cards are "coming soon"). Monthly payment is a payment prompt on the phone
  (STK Push) the day before renewal, with a 7-day grace period before the account goes read-only. Data is
  never deleted for non-payment.
- **Yearly prepayment** with two months free suits agents' cash flow after commission months, and saves us
  12 failed prompts a year.
- **M-Pesa Ratiba** (standing orders) can automate monthly payments later; it needs a commercial agreement
  with Safaricom.
- We issue our own receipt (and an eTIMS invoice once we are registered) for every subscription payment.

## What this could earn (illustrative)

| Year-1 target | Customers | Average (KES) | Monthly revenue (KES) |
|---|---|---|---|
| Agents | 300 | 1,350 (mix of founding and full price) | 405,000 |
| Agencies | 20 | 4,500 | 90,000 |
| Businesses | 150 | 999 | 150,000 |
| **Total** | | | **≈ 645,000 / month** |

Running costs at this scale are small:
- one VM (about KES 6,000–12,000 a month);
- email, about KES 1,500;
- backups and storage, about KES 2,000;
- M-Pesa fees on subscription collections.

## Before committing

1. Show the plans to **10–15 agents** (mix of new and established) and **5 principal agencies**. Ask what
   they pay now for tools, airtime and assistants, and whether they would pay KES 1,500. Watch for
   KES 1,000 as a psychological ceiling.
2. Launch the founding offer with the 14-day trial, and measure:
   - trial to paid within 30 days of sign-up (target 15% or more);
   - churn after month 3 (target under 5% a month);
   - which features paying agents use (renewals and reminders are expected to drive retention).
3. Revisit after 3 months of real data. Raising the price for new customers is easier than lowering it, so
   the founding discount keeps early customers happy if the full price moves up.
