# Landing page: research and design plan

Status: built 2026-10-19 (public home `/` for signed-out visitors). Revisit once real agents and testimonials exist.

## Who it is for and what it must do

- **Visitor:** a licensed Kenyan insurance agent (about 15,000 of them, see `docs/PRICING.md`), usually on an
  Android phone and mobile data, often arriving from a WhatsApp group link. Second audience: SME owners who
  need quotes, invoices and M-Pesa collection (the Business plan).
- **Job:** get them to start the 30-day trial (no card), or download the Android app. Sign-in stays one tap away.

## Research findings (October 2026)

| Finding | What we do with it | Source |
|---|---|---|
| The 2026 SaaS hero shows the product working, not a description of it | The hero plays one real workflow: a comparison quote shared on WhatsApp and accepted by the client | [saasframe.io](https://www.saasframe.io/blog/10-saas-landing-page-trends-for-2026-with-real-examples) |
| Motion in 2026 is about rhythm and restraint; flashy effects read as noise | One orchestrated hero moment; one scroll-linked line; everything else moves only when the visitor acts | [wannathis.one](https://wannathis.one/blog/top-ui-design-trends-for-2026-you-cant-ignore), [uxpin.com](https://www.uxpin.com/studio/blog/landing-page-design-trends/) |
| Animated SVG heroes doubled on B2B pages (11% → 23%); practitioners are cutting heavy ones for speed | No video, no Lottie, no animation library: CSS keyframes on HTML we already render | [pravinkumar.co](https://www.pravinkumar.co/blog/stopped-animated-svg-backgrounds-webflow-hero-2026) |
| Core Web Vitals still affect search and ad quality; each extra second of load costs conversions | Server-rendered page, two tiny client islands, no images, fonts already self-hosted | [moburst.com](https://www.moburst.com/blog/landing-page-design-trends-2026/) |
| CSS scroll-driven animations (`animation-timeline: view()`) run off the main thread in Chrome/Edge and Safari 26; Firefox support is incomplete | Used only inside `@supports (animation-timeline: view())` and `prefers-reduced-motion: no-preference`; without it the page is complete and static | MDN, caniuse |
| Kenyan Android phones run Android 11–16 (Android 13 most common, about 17.6%) | Target mid-range Chrome on Android; test at 390 px | [StatCounter](https://gs.statcounter.com/android-version-market-share/mobile/kenya) |
| No Kenyan product serves the individual agent with public prices; foreign CRMs cost KES 6,000–30,000 a user | Show prices openly, in KES, next to the call to action | `docs/PRICING.md` |

What we deliberately do **not** do: invent testimonials or customer logos (there are none yet), use real insurers'
names or logos (example insurers only, labelled), or claim legal compliance that an adviser has not signed off (D4, D5).

## Design plan

**Colour** (the product's own tokens, so the page and the app feel like one thing):
paper `#f6f7f4`, ink `#17302b`, acacia `#0e6b5c` (actions), maize `#f2b705` (the stamp, focus, progress),
line `#d6ddd8`. Dark mode follows the app's dark tokens.

**Type:** Bricolage Grotesque with its optical-size axis loaded, so the big headlines take the tighter display
cut automatically; Atkinson Hyperlegible for body text (designed for low-vision legibility, which helps on
small, bright phone screens outdoors). Body lines stay under 70 characters.

**The one bold element:** the agency rubber stamp. In the hero it comes down on the accepted quote; it reappears
on the documents section with the visitor-facing agency name. Nothing else competes with it.

**Layout** (left-aligned, asymmetric; each section takes the shape of its content rather than a card grid):

```
┌───────────────────────────────────────────────────────────────┐
│ BrokerOS      Features  Pricing  Android app   Sign in [Start]│
├───────────────────────────────┬───────────────────────────────┤
│ Never miss a renewal again.   │  ┌ Comprehensive motor ──────┐│
│ sub: what BrokerOS does       │  │ Mlima     87,933.75       ││
│ [Start 30 days free] Pricing  │  │ Pwani ●   100,490.00  rec ││
│ No card. Pay by M-Pesa later. │  │ Baobab   106,768.13       ││
│                               │  └───────────────────────────┘│
│                               │   WhatsApp bubble → Accept     │
│                               │        (STAMP: Accepted)       │
├───────────────────────────────┴───────────────────────────────┤
│ How a sale moves: 1 Lead 2 Quote 3 Accept 4 Policy 5 Renewal 6│
│ Commission   (a real sequence, so it is numbered; the maize   │
│ line fills as you scroll)                                      │
├───────────────────────────────────────────────────────────────┤
│ Renewals board (due / contacted / quoted / renewed + KES)      │
├──────────────────────────┬────────────────────────────────────┤
│ Commission slip (gross,  │ M-Pesa: money lands in your own    │
│ WHT, net) as a receipt   │ Paybill; we never hold it          │
├──────────────────────────┴────────────────────────────────────┤
│ Documents: 12 designs, your stamp and logo                     │
│ Android app: offline, reminders → /download                    │
│ For businesses: invoices, VAT, credit notes, eTIMS reference   │
├───────────────────────────────────────────────────────────────┤
│ Pricing: Free / Agent / Agency / Business, monthly ⇄ yearly,   │
│ founding offer: first 100 paying agents 50% off for 12 months  │
├───────────────────────────────────────────────────────────────┤
│ Questions (details/summary)                                    │
│ Final call to action on ink                                    │
└───────────────────────────────────────────────────────────────┘
```

**Motion budget:**
1. *Hero sequence* (plays once on load, about 5 s, CSS keyframes with staggered delays): quote options arrive,
   the recommended one is marked, the WhatsApp message goes, the client taps Accept, the stamp lands,
   "Policy active, renewal reminder set" appears. A "Play again" button replays it (visitor-triggered).
2. *Scroll-linked line* on the sales sequence, filling as the visitor reads down (progressive enhancement).
3. *Visitor-triggered only:* the monthly/yearly price switch and the questions opening.
With `prefers-reduced-motion: reduce` every element shows its final state at once.

## Review against generic defaults

- Rejected a "big number + small label + gradient" hero: the subject's most characteristic moment is a client
  accepting a quote on WhatsApp, so that is the hero.
- Rejected identical feature cards: each section uses the form of its subject (a board, a slip, a stamp, a phone).
- No all-caps eyebrow labels, no arrows appended to buttons, no single highlighted word in headlines, no
  middle-dot meta strings. Numbers appear only on the sales sequence, which really is a sequence.
- Kept the product's own palette (green and maize on cool paper) instead of a new "marketing" palette: the
  page should look like the app agents will use.

## Routing

`/` is the dashboard for signed-in users. The web proxy rewrites `/` to `/welcome` for visitors without a
session cookie, so the address bar keeps `/`. `/welcome` is public. The canonical URL is `/`.
