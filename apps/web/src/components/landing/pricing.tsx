"use client";

import { Check } from "lucide-react";
import Link from "next/link";
import { useState } from "react";

import { cn } from "@/lib/utils";

type Cycle = "monthly" | "yearly";

// Mirrors apps/api/app/modules/subscriptions/plans.py (docs/PRICING.md). KES, VAT-inclusive.
const PLANS = [
  {
    name: "Agent",
    who: "For one working agent",
    monthly: 1500,
    yearly: 15000,
    founding: 750,
    seats: "1 user, unlimited clients",
    features: [
      "Compare insurers on one quote",
      "Renewal reminders to clients",
      "Commission and WHT tracking",
      "Import your book from Excel",
      "Your logo, colours and stamp",
      "Support on WhatsApp",
    ],
  },
  {
    name: "Agency",
    who: "For agencies with a team",
    monthly: 4500,
    yearly: 45000,
    founding: 2250,
    seats: "5 users, then KES 700 per extra user a month",
    features: [
      "Everything in Agent",
      "Team roles: agents see only their own clients",
      "Renewals and tasks shown per agent",
      "All 12 document designs",
      "Priority WhatsApp support and an onboarding call",
    ],
    trial: true,
  },
  {
    name: "Business",
    who: "For businesses: quotes and invoices only",
    monthly: 999,
    yearly: 9990,
    seats: "3 users",
    features: [
      "Sales quotes, invoices and receipts",
      "VAT and credit notes",
      "M-Pesa payments and reminders",
      "eTIMS reference on invoices",
    ],
  },
] as const;

const kes = (n: number) => `KES ${n.toLocaleString("en-KE")}`;

export function Pricing() {
  const [cycle, setCycle] = useState<Cycle>("monthly");
  return (
    <div className="grid gap-8">
      <div
        role="radiogroup"
        aria-label="Billing period"
        className="bg-card inline-flex justify-self-start rounded-full border p-1"
      >
        {(["monthly", "yearly"] as const).map((value) => (
          <button
            key={value}
            type="button"
            role="radio"
            aria-checked={cycle === value}
            onClick={() => setCycle(value)}
            className={cn(
              "rounded-full px-4 py-2 text-sm font-bold transition-colors",
              cycle === value
                ? "bg-ink text-[#f6f7f4] dark:bg-[#e8efec] dark:text-[#0f1f1c]"
                : "text-muted-foreground hover:text-foreground",
            )}
          >
            {value === "monthly" ? "Monthly" : "Yearly, 2 months free"}
          </button>
        ))}
      </div>

      <ul className="bg-border grid gap-px overflow-hidden rounded-xl border md:grid-cols-3">
        {PLANS.map((plan) => {
          const amount = cycle === "monthly" ? plan.monthly : plan.yearly;
          const highlighted = "trial" in plan;
          return (
            <li
              key={plan.name}
              className={cn(
                "bg-card flex flex-col gap-4 p-6",
                highlighted && "bg-[color-mix(in_oklab,var(--maize)_10%,var(--card))]",
              )}
            >
              <div>
                <h3 className="text-xl">{plan.name}</h3>
                <p className="text-muted-foreground text-sm">{plan.who}</p>
              </div>
              <p key={cycle} className="lp-price">
                <span className="tabular font-heading text-3xl font-bold">{kes(amount)}</span>{" "}
                <span className="text-muted-foreground text-sm">
                  {cycle === "monthly" ? "a month" : "a year"}
                </span>
              </p>
              {"founding" in plan && cycle === "monthly" && (
                <p className="text-sm">
                  Founding members pay <strong className="tabular">{kes(plan.founding)}</strong> a
                  month for the first year.
                </p>
              )}
              <p className="text-sm font-bold">{plan.seats}</p>
              <ul className="grid gap-2 text-sm">
                {plan.features.map((feature) => (
                  <li key={feature} className="flex gap-2">
                    <Check
                      aria-hidden="true"
                      className="text-acacia mt-0.5 size-4 shrink-0 dark:text-[#7fd6c2]"
                    />
                    {feature}
                  </li>
                ))}
              </ul>
              {highlighted && (
                <p className="mt-auto text-sm font-bold">
                  Every new account gets 14 days of Agency free.
                </p>
              )}
            </li>
          );
        })}
      </ul>

      <div className="flex flex-wrap items-center gap-x-6 gap-y-3">
        <Link
          href="/sign-up"
          className="bg-primary text-primary-foreground hover:bg-primary/90 inline-flex h-12 items-center rounded-md px-6 font-bold"
        >
          Start 14 days free
        </Link>
        <p className="text-muted-foreground max-w-prose text-sm">
          No card needed. Pay by M-Pesa when you&apos;re ready; prices include VAT. If you
          don&apos;t choose a plan, the account becomes read-only after the trial and your data
          stays.
        </p>
      </div>
    </div>
  );
}
