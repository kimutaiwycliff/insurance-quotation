import {
  BellRing,
  CircleHelp,
  CloudOff,
  Download,
  FileSpreadsheet,
  Plus,
  ShieldCheck,
  Smartphone,
  Users,
} from "lucide-react";
import type { Metadata } from "next";
import { headers } from "next/headers";
import Link from "next/link";

import { Seal } from "@/components/brand/seal";
import { HeroDemo } from "@/components/landing/hero-demo";
import { Pricing } from "@/components/landing/pricing";

import "./landing.css";

const DESCRIPTION =
  "BrokerOS is the office for Kenyan insurance agents: clients, comparison quotes, policies, renewal reminders and commission, with M-Pesa built in. Start 14 days free.";

/** Absolute canonical URL from the request (Caddy forwards Host and the scheme), so no extra setting is needed. */
export async function generateMetadata(): Promise<Metadata> {
  const headerList = await headers();
  const host = headerList.get("x-forwarded-host") ?? headerList.get("host") ?? "localhost:3000";
  const scheme =
    headerList.get("x-forwarded-proto") ?? (host.startsWith("localhost") ? "http" : "https");
  const title = "BrokerOS: never miss a renewal again";
  return {
    metadataBase: new URL(`${scheme}://${host}`),
    title: { absolute: title },
    description: DESCRIPTION,
    alternates: { canonical: "/" },
    openGraph: { title, description: DESCRIPTION, type: "website", locale: "en_KE", url: "/" },
  };
}

// The steps a sale really goes through, in order, so they are numbered.
const FLOW = [
  {
    title: "Capture the lead",
    body: "Add a prospect in seconds from a call or a WhatsApp chat, and set a task so you follow up on time.",
  },
  {
    title: "Compare insurers",
    body: "Pick the products and the calculator works out each premium with the training levy, PHCF and stamp duty. Add loadings, discounts and optional benefits.",
  },
  {
    title: "The client accepts on WhatsApp",
    body: "Send one link. Your client compares the options on their phone and accepts one. You see it straight away.",
  },
  {
    title: "Issue the policy",
    body: "Turn the accepted option into a policy, record the payment and activate cover once the premium is in.",
  },
  {
    title: "Renew on time",
    body: "Every policy lands on the renewals board before it expires. Remind clients by WhatsApp or email and quote the renewal in two taps.",
  },
  {
    title: "Collect your commission",
    body: "Record what each insurer pays you. BrokerOS works out the 10% WHT, tracks the certificates and shows what is still owed.",
  },
];

const BOARD = [
  {
    stage: "Due",
    count: 7,
    premium: "412,300",
    items: ["Achieng O., motor, 12 days", "Kiprono Hardware, fire, 20 days"],
  },
  { stage: "Contacted", count: 4, premium: "198,050", items: ["Mwangi family, medical, 9 days"] },
  { stage: "Quoted", count: 3, premium: "156,400", items: ["Otieno Transport, 3 lorries, 5 days"] },
  {
    stage: "Renewed",
    count: 11,
    premium: "640,900",
    items: ["Njeri W., motor", "Baraka School, WIBA"],
  },
];

const FAQ = [
  {
    q: "Do I need a card to start?",
    a: "No. Every new account gets 14 days of the Agency plan, with no card. When you choose a plan you pay by M-Pesa. If you don't, the account becomes read-only: you can still see and download everything, and paying unlocks it again.",
  },
  {
    q: "Does my clients' money pass through BrokerOS?",
    a: "Never. Premiums and invoice payments go straight to your own Paybill or till, or to the insurer. BrokerOS sends the M-Pesa prompt and matches the payment to the right policy or invoice.",
  },
  {
    q: "I keep my book in Excel. Can I bring it in?",
    a: "Yes. Upload your spreadsheet of clients and policies, match the columns, check the preview and import. Renewal dates go straight onto the board.",
  },
  {
    q: "Can my agents see each other's clients?",
    a: "Not unless you allow it. On the Agency plan each agent sees only their own clients, and you see everything. Each agency's data is kept completely separate from every other agency's.",
  },
  {
    q: "Does it work on my phone without data?",
    a: "The Android app keeps your recent clients, policies and renewals on the phone. Changes you make offline are sent when you are back online, and it notifies you about renewals and tasks.",
  },
  {
    q: "Are levies and stamp duty worked out for me?",
    a: "Yes, from Kenyan rules kept as data: training levy, PHCF and stamp duty by class of business. You can still enter an insurer's own figure when it differs, and the quote shows the full breakdown.",
  },
];

const jsonLd = {
  "@context": "https://schema.org",
  "@type": "SoftwareApplication",
  name: "BrokerOS",
  applicationCategory: "BusinessApplication",
  operatingSystem: "Web, Android",
  description: DESCRIPTION,
  offers: [
    { "@type": "Offer", name: "Agent", price: "1500", priceCurrency: "KES" },
    { "@type": "Offer", name: "Agency", price: "4500", priceCurrency: "KES" },
    { "@type": "Offer", name: "Business", price: "999", priceCurrency: "KES" },
  ],
};

const container = "mx-auto w-full max-w-6xl px-5 sm:px-8";

/** Public home for signed-out visitors (proxy.ts rewrites "/" here). Plan and research: docs/LANDING_PAGE.md. */
export default function LandingPage() {
  // overflow-x-clip: the hero stamp starts large near the edge and must not widen the page on phones.
  return (
    <div className="bg-background min-h-dvh overflow-x-clip">
      <script
        type="application/ld+json"
        dangerouslySetInnerHTML={{ __html: JSON.stringify(jsonLd) }}
      />
      <a
        href="#main"
        className="focus:bg-card sr-only focus:not-sr-only focus:absolute focus:top-4 focus:left-4 focus:z-50 focus:rounded-md focus:px-4 focus:py-2"
      >
        Skip to content
      </a>

      <header className="bg-background/90 supports-[backdrop-filter]:bg-background/75 sticky top-0 z-40 border-b backdrop-blur">
        <nav aria-label="Main" className={`${container} flex h-16 items-center gap-6`}>
          <Link href="/" className="font-heading flex items-center gap-2 text-lg font-bold">
            <Seal name="BrokerOS" size={28} />
            BrokerOS
          </Link>
          <ul className="ml-auto hidden items-center gap-6 text-sm font-bold md:flex">
            <li>
              <a href="#how" className="hover:text-acacia">
                How it works
              </a>
            </li>
            <li>
              <a href="#pricing" className="hover:text-acacia">
                Pricing
              </a>
            </li>
            <li>
              <Link href="/download" className="hover:text-acacia">
                Android app
              </Link>
            </li>
          </ul>
          <div className="ml-auto flex items-center gap-2 md:ml-0">
            <Link
              href="/sign-in"
              className="hover:bg-accent rounded-md px-3 py-2 text-sm font-bold"
            >
              Sign in
            </Link>
            <Link
              href="/sign-up"
              className="bg-primary text-primary-foreground hover:bg-primary/90 rounded-md px-4 py-2 text-sm font-bold"
            >
              Start free
            </Link>
          </div>
        </nav>
      </header>

      <main id="main">
        {/* Hero: the promise on the left, the product doing it on the right. */}
        <section
          className={`${container} grid items-center gap-12 pt-12 pb-20 sm:pt-16 lg:grid-cols-[minmax(0,1.1fr)_minmax(0,1fr)] lg:pb-28`}
        >
          <div className="lp-in max-w-xl">
            <h1 className="lp-display text-[clamp(2.75rem,8vw,5.75rem)] text-balance">
              Never miss a renewal again.
            </h1>
            <p className="text-muted-foreground mt-6 max-w-[34rem] text-lg sm:text-xl">
              BrokerOS is the office for Kenyan insurance agents. Keep your clients, quotes,
              policies and commission in one place. Clients accept quotes on WhatsApp, and BrokerOS
              reminds you before every cover expires.
            </p>
            <div className="mt-8 flex flex-wrap items-center gap-3">
              <Link
                href="/sign-up"
                className="bg-primary text-primary-foreground hover:bg-primary/90 inline-flex h-12 items-center rounded-md px-6 text-base font-bold"
              >
                Start 14 days free
              </Link>
              <a
                href="#pricing"
                className="bg-card hover:bg-accent inline-flex h-12 items-center rounded-md border px-5 font-bold"
              >
                See pricing
              </a>
            </div>
            <p className="text-muted-foreground mt-4 text-sm">
              No card needed. Pay by M-Pesa when you&apos;re ready.
            </p>
          </div>
          <HeroDemo />
        </section>

        {/* The sales sequence. */}
        <section id="how" aria-labelledby="how-heading" className="bg-card border-y py-20 lg:py-28">
          <div className={`${container} grid gap-12 lg:grid-cols-[minmax(0,2fr)_minmax(0,3fr)]`}>
            <div className="lg:sticky lg:top-28 lg:self-start">
              <h2 id="how-heading" className="lp-display text-[clamp(2.25rem,5vw,3.75rem)]">
                From first call to commission.
              </h2>
              <p className="text-muted-foreground mt-5 max-w-md text-lg">
                The whole life of a sale in one place, so nothing lives on scraps of paper, in your
                head or in a WhatsApp chat you can&apos;t find.
              </p>
            </div>
            <ol className="lp-flow grid gap-9">
              {FLOW.map((step, index) => (
                <li
                  key={step.title}
                  className="relative grid grid-cols-[2.25rem_minmax(0,1fr)] gap-5"
                >
                  <span className="border-maize bg-card font-heading tabular relative z-10 grid size-9 place-items-center rounded-full border-2 font-bold">
                    {index + 1}
                  </span>
                  <div>
                    <h3 className="text-xl">{step.title}</h3>
                    <p className="text-muted-foreground mt-1.5 max-w-prose">{step.body}</p>
                  </div>
                </li>
              ))}
            </ol>
          </div>
        </section>

        {/* Renewals board. */}
        <section aria-labelledby="renewals-heading" className="py-20 lg:py-28">
          <div className={container}>
            <div className="max-w-2xl">
              <h2 id="renewals-heading" className="lp-display text-[clamp(2.25rem,5vw,3.75rem)]">
                Renewals come to you.
              </h2>
              <p className="text-muted-foreground mt-5 text-lg">
                One renewal&apos;s commission pays for a month of BrokerOS. The board shows every
                policy expiring in the next 30, 60 or 90 days, what it is worth and who you have
                already called.
              </p>
            </div>
            <figure className="mt-10" aria-labelledby="board-caption">
              <ul className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
                {BOARD.map((column) => (
                  <li key={column.stage} className="bg-muted/60 rounded-xl border p-4">
                    <p className="flex items-baseline justify-between gap-2">
                      <span className="font-bold">{column.stage}</span>
                      <span className="text-muted-foreground tabular text-sm">
                        {column.count} policies
                      </span>
                    </p>
                    <p className="tabular font-heading mt-1 text-2xl font-bold">
                      KES {column.premium}
                    </p>
                    <ul className="mt-4 grid gap-2">
                      {column.items.map((item) => (
                        <li key={item} className="bg-card rounded-md border px-3 py-2 text-sm">
                          {item}
                        </li>
                      ))}
                    </ul>
                  </li>
                ))}
              </ul>
              <figcaption id="board-caption" className="text-muted-foreground mt-3 text-xs">
                Example renewals board for the next 30 days. Names and amounts are illustrative.
              </figcaption>
            </figure>
          </div>
        </section>

        {/* Money: commission slip and M-Pesa. */}
        <section
          aria-labelledby="money-heading"
          className="bg-ink py-20 text-[#f6f7f4] lg:py-28 dark:bg-[#132824]"
        >
          <div className={`${container} grid items-center gap-12 lg:grid-cols-2`}>
            <div>
              <h2 id="money-heading" className="lp-display text-[clamp(2.25rem,5vw,3.75rem)]">
                Know what you are owed. Get paid to your own Paybill.
              </h2>
              <p className="mt-5 max-w-lg text-lg text-[#c9d6d1]">
                Match each insurer&apos;s commission payment to the policies it covers, with
                withholding tax and certificates tracked for your tax return. Clients pay premiums
                and invoices by M-Pesa straight to your Paybill or till, and BrokerOS matches each
                payment for you.
              </p>
              <p className="mt-6 flex max-w-lg gap-3 rounded-lg border border-[#2f4b45] p-4 text-[#e8efec]">
                <ShieldCheck aria-hidden="true" className="text-maize mt-0.5 size-5 shrink-0" />
                <span>
                  BrokerOS never holds your money or your clients&apos; money. It only sends the
                  payment prompt and records the result.
                </span>
              </p>
            </div>
            <figure
              aria-labelledby="slip-caption"
              className="justify-self-center lg:justify-self-end"
            >
              <div className="lp-slip text-ink w-full max-w-sm px-6 pt-9 pb-8 dark:text-[#e8efec]">
                <p className="font-heading text-lg font-bold">Commission received</p>
                <p className="text-muted-foreground text-sm">Pwani Assurance, October</p>
                <dl className="tabular mt-5 grid gap-2 text-sm">
                  <div className="flex justify-between gap-4">
                    <dt>Achieng Otieno, motor</dt>
                    <dd>8,750.00</dd>
                  </div>
                  <div className="flex justify-between gap-4">
                    <dt>Kiprono Hardware, fire</dt>
                    <dd>4,200.00</dd>
                  </div>
                  <div className="flex justify-between gap-4 border-t border-dashed pt-2 font-bold">
                    <dt>Gross commission</dt>
                    <dd>12,950.00</dd>
                  </div>
                  <div className="text-muted-foreground flex justify-between gap-4">
                    <dt>WHT withheld, 10%</dt>
                    <dd>−1,295.00</dd>
                  </div>
                  <div className="font-heading flex justify-between gap-4 border-t pt-2 text-lg font-bold">
                    <dt>Net to you (KES)</dt>
                    <dd>11,655.00</dd>
                  </div>
                </dl>
                <p className="text-muted-foreground mt-4 text-xs">WHT certificate: received</p>
              </div>
              <figcaption id="slip-caption" className="mt-3 text-center text-xs text-[#c9d6d1]">
                Example commission receipt. Figures are illustrative.
              </figcaption>
            </figure>
          </div>
        </section>

        {/* Documents with the agency's stamp, and the rest of the toolkit. */}
        <section aria-labelledby="docs-heading" className="py-20 lg:py-28">
          <div
            className={`${container} grid items-center gap-12 lg:grid-cols-[minmax(0,1fr)_minmax(0,1.2fr)]`}
          >
            <div className="relative grid place-items-center py-6">
              <Seal name="Wanjiku Insurance Agency" size={220} />
            </div>
            <div>
              <h2 id="docs-heading" className="lp-display text-[clamp(2.25rem,5vw,3.75rem)]">
                Paperwork that looks like your agency.
              </h2>
              <p className="text-muted-foreground mt-5 max-w-xl text-lg">
                Quotes, invoices, receipts and credit notes go out as clean PDFs with your logo,
                colours and stamp. Choose from 12 designs, or send them without a logo at all.
              </p>
              <ul className="mt-8 grid gap-5 sm:grid-cols-2">
                <li className="flex gap-3">
                  <FileSpreadsheet
                    aria-hidden="true"
                    className="text-acacia mt-0.5 size-5 shrink-0 dark:text-[#7fd6c2]"
                  />
                  <span>
                    <strong className="block">Bring your book from Excel</strong>
                    <span className="text-muted-foreground">
                      Clients and policies, with renewal dates.
                    </span>
                  </span>
                </li>
                <li className="flex gap-3">
                  <Users
                    aria-hidden="true"
                    className="text-acacia mt-0.5 size-5 shrink-0 dark:text-[#7fd6c2]"
                  />
                  <span>
                    <strong className="block">Work as a team</strong>
                    <span className="text-muted-foreground">
                      Roles for agents, accounts staff and assistants.
                    </span>
                  </span>
                </li>
                <li className="flex gap-3">
                  <BellRing
                    aria-hidden="true"
                    className="text-acacia mt-0.5 size-5 shrink-0 dark:text-[#7fd6c2]"
                  />
                  <span>
                    <strong className="block">Tasks and reminders</strong>
                    <span className="text-muted-foreground">
                      Follow-ups and renewals, never forgotten.
                    </span>
                  </span>
                </li>
                <li className="flex gap-3">
                  <CircleHelp
                    aria-hidden="true"
                    className="text-acacia mt-0.5 size-5 shrink-0 dark:text-[#7fd6c2]"
                  />
                  <span>
                    <strong className="block">Help built in</strong>
                    <span className="text-muted-foreground">
                      Search any question inside the app.
                    </span>
                  </span>
                </li>
              </ul>
            </div>
          </div>
        </section>

        {/* Android app and the Business plan. */}
        <section aria-label="Android app and BrokerOS for businesses" className="bg-card border-y">
          <div className={`${container} grid divide-y lg:grid-cols-2 lg:divide-x lg:divide-y-0`}>
            <div className="py-16 lg:pr-12">
              <Smartphone aria-hidden="true" className="text-acacia size-8 dark:text-[#7fd6c2]" />
              <h2 className="mt-4 text-3xl">Your agency in your pocket</h2>
              <p className="text-muted-foreground mt-3 max-w-md">
                The Android app has everything the web app has. It keeps working when the network
                drops, tells you when a renewal is due and updates itself.
              </p>
              <ul className="mt-5 grid gap-2 text-sm">
                <li className="flex gap-2">
                  <CloudOff
                    aria-hidden="true"
                    className="text-acacia size-4 shrink-0 dark:text-[#7fd6c2]"
                  />{" "}
                  Works offline, syncs when you are back
                </li>
                <li className="flex gap-2">
                  <BellRing
                    aria-hidden="true"
                    className="text-acacia size-4 shrink-0 dark:text-[#7fd6c2]"
                  />{" "}
                  Renewal and task notifications
                </li>
                <li className="flex gap-2">
                  <ShieldCheck
                    aria-hidden="true"
                    className="text-acacia size-4 shrink-0 dark:text-[#7fd6c2]"
                  />{" "}
                  Two-step sign-in and checked updates
                </li>
              </ul>
              <Link
                href="/download"
                className="bg-background hover:bg-accent mt-6 inline-flex h-11 items-center gap-2 rounded-md border px-5 font-bold"
              >
                <Download aria-hidden="true" className="size-4" /> Get the Android app
              </Link>
            </div>
            <div className="py-16 lg:pl-12">
              <p className="font-heading text-3xl font-bold" aria-hidden="true">
                KES 999
              </p>
              <h2 className="mt-4 text-3xl">Not an insurance agent?</h2>
              <p className="text-muted-foreground mt-3 max-w-md">
                BrokerOS Business is quoting and invoicing for small businesses, for KES 999 a month
                with 3 users: sales quotes with optional extras, invoices with VAT, credit notes,
                receipts and M-Pesa payment prompts that match themselves.
              </p>
              <Link
                href="/sign-up"
                className="bg-background hover:bg-accent mt-6 inline-flex h-11 items-center rounded-md border px-5 font-bold"
              >
                Start with Business
              </Link>
            </div>
          </div>
        </section>

        {/* Pricing. */}
        <section
          id="pricing"
          aria-labelledby="pricing-heading"
          className="scroll-mt-20 py-20 lg:py-28"
        >
          <div className={container}>
            <div className="flex flex-wrap items-end justify-between gap-6">
              <div className="max-w-2xl">
                <h2 id="pricing-heading" className="lp-display text-[clamp(2.25rem,5vw,3.75rem)]">
                  Priced for one agent, not a head office.
                </h2>
                <p className="text-muted-foreground mt-5 text-lg">
                  Prices in shillings, VAT included. Change or cancel any time.
                </p>
              </div>
              <p className="border-maize flex max-w-sm items-center gap-4 rounded-xl border-2 p-4">
                <Seal name="Founding member" size={64} />
                <span>
                  <strong className="block">Founding members: half price for a year</strong>
                  <span className="text-muted-foreground text-sm">
                    For the first 100 agents and agencies who subscribe, on monthly payments.
                  </span>
                </span>
              </p>
            </div>
            <div className="mt-10">
              <Pricing />
            </div>
          </div>
        </section>

        {/* Questions. */}
        <section aria-labelledby="faq-heading" className="border-t py-20 lg:py-28">
          <div className={`${container} grid gap-10 lg:grid-cols-[minmax(0,2fr)_minmax(0,3fr)]`}>
            <h2 id="faq-heading" className="lp-display text-[clamp(2.25rem,5vw,3.75rem)]">
              Questions agents ask.
            </h2>
            <div className="lp-faq divide-y border-y">
              {FAQ.map((item) => (
                <details key={item.q} className="group">
                  <summary className="flex items-center justify-between gap-4 py-5 text-lg font-bold">
                    {item.q}
                    <Plus
                      aria-hidden="true"
                      className="lp-plus text-acacia size-5 shrink-0 dark:text-[#7fd6c2]"
                    />
                  </summary>
                  <p className="text-muted-foreground max-w-prose pb-5">{item.a}</p>
                </details>
              ))}
            </div>
          </div>
        </section>

        {/* Last call. */}
        <section
          aria-labelledby="cta-heading"
          className="bg-ink py-20 text-[#f6f7f4] dark:bg-[#132824]"
        >
          <div className={`${container} flex flex-wrap items-center justify-between gap-8`}>
            <div className="max-w-xl">
              <h2 id="cta-heading" className="lp-display text-[clamp(2.25rem,5vw,3.75rem)]">
                Your next renewal is already on the way.
              </h2>
              <p className="mt-4 text-lg text-[#c9d6d1]">
                Set up your agency in five minutes and import your book today.
              </p>
            </div>
            <div className="flex flex-wrap gap-3">
              <Link
                href="/sign-up"
                className="bg-maize text-ink inline-flex h-12 items-center rounded-md px-6 font-bold hover:bg-[#ffc824]"
              >
                Start 14 days free
              </Link>
              <Link
                href="/sign-in"
                className="inline-flex h-12 items-center rounded-md border border-[#4b6b64] px-5 font-bold hover:bg-white/10"
              >
                Sign in
              </Link>
            </div>
          </div>
        </section>
      </main>

      <footer className="text-muted-foreground py-10 text-sm">
        <div className={`${container} flex flex-wrap items-center justify-between gap-4`}>
          <p>BrokerOS, made in Kenya for insurance agents and small businesses.</p>
          <ul className="flex flex-wrap gap-5">
            <li>
              <Link href="/download" className="hover:text-foreground">
                Android app
              </Link>
            </li>
            <li>
              <Link href="/sign-in" className="hover:text-foreground">
                Sign in
              </Link>
            </li>
            <li>
              <Link href="/sign-up" className="hover:text-foreground">
                Create an account
              </Link>
            </li>
          </ul>
        </div>
      </footer>
    </div>
  );
}
