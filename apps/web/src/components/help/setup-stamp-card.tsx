"use client";

import { Building2, Check, Landmark, type LucideIcon, Palette, ShieldCheck, Smartphone, UserPlus, Users, FileText } from "lucide-react";
import Link from "next/link";

import { Seal } from "@/components/brand/seal";
import { useCan, useMe } from "@/components/shell/me-context";
import { hasFeature } from "@/components/shell/nav";
import { useBrandingGet } from "@/lib/api/generated/branding/branding";
import { useDashboardGet } from "@/lib/api/generated/dashboard/dashboard";
import { useInsurersList } from "@/lib/api/generated/insurers/insurers";
import { useMembersList } from "@/lib/api/generated/members/members";
import { useMpesaConnectionGet } from "@/lib/api/generated/mpesa/mpesa";
import { useOrganizationGet } from "@/lib/api/generated/organization/organization";
import { useQuotesList } from "@/lib/api/generated/quotes/quotes";
import { cn } from "@/lib/utils";

interface Step {
  key: string;
  label: string;
  href: string;
  icon: LucideIcon;
  done: boolean;
}

/**
 * "Your first week": the setup steps that matter, each stamped when the agency's own data shows it is done.
 * Only steps the member's plan and role allow are shown.
 */
export function SetupStampCard() {
  const me = useMe();
  const has = (feature: string) => hasFeature(me.features, feature);
  const canOrg = useCan("org:read");
  const canBrand = useCan("branding:manage") && has("branding");
  const canAllClients = useCan("client:read:all");
  const canOwnClients = useCan("client:read:own");
  const canClients = canAllClients || canOwnClients;
  const canInsurers = useCan("insurer:read") && has("insurance");
  const canTeam = useCan("member:read") && has("team");

  const org = useOrganizationGet({ query: { enabled: canOrg } });
  const branding = useBrandingGet({ query: { enabled: canBrand } });
  const board = useDashboardGet({ query: { enabled: canClients } });
  const insurers = useInsurersList(undefined, { query: { enabled: canInsurers } });
  const quotes = useQuotesList({ limit: 1 }, { query: { enabled: canInsurers && canClients } });
  const mpesa = useMpesaConnectionGet({ query: { enabled: canOrg } });
  const members = useMembersList({ query: { enabled: canTeam } });

  const steps: Step[] = [
    canOrg && { key: "details", label: "Add your KRA PIN and licence", href: "/settings/organization", icon: Building2, done: Boolean(org.data?.tax_pin) },
    canBrand && { key: "brand", label: "Upload your logo", href: "/settings/branding", icon: Palette, done: Boolean(branding.data?.logo_document_id) },
    canClients && { key: "client", label: "Add your first client", href: "/clients", icon: Users, done: (board.data?.clients ?? 0) > 0 },
    canInsurers && { key: "insurer", label: "Add an insurer and product", href: "/settings/insurers", icon: Landmark, done: (insurers.data?.length ?? 0) > 0 },
    canInsurers && canClients && { key: "quote", label: "Send your first quote", href: "/quotes", icon: FileText, done: (quotes.data?.length ?? 0) > 0 },
    canOrg && { key: "mpesa", label: "Connect M-Pesa", href: "/settings/payments", icon: Smartphone, done: mpesa.data?.status === "active" },
    canTeam && { key: "team", label: "Invite a colleague", href: "/settings/members", icon: UserPlus, done: (members.data?.length ?? 0) > 1 },
    { key: "security", label: "Turn on two-factor sign-in", href: "/settings/security", icon: ShieldCheck, done: me.mfa_enrolled },
  ].filter((s): s is Step => Boolean(s));

  const loading = org.isLoading || board.isLoading || insurers.isLoading || mpesa.isLoading;
  const done = steps.filter((s) => s.done).length;
  const percent = steps.length ? Math.round((done / steps.length) * 100) : 0;
  const complete = done === steps.length;

  return (
    <section aria-labelledby="setup-heading" className="help-rise grid gap-5 rounded-xl border bg-card p-5 sm:p-6">
      <div className="flex flex-wrap items-center gap-4">
        <Seal name={me.tenant.name} size={52} className="text-primary" />
        <div className="grid flex-1 gap-0.5">
          <h2 id="setup-heading" className="text-xl">
            {complete ? "Every stamp collected" : "Your first week"}
          </h2>
          <p className="text-sm text-muted-foreground">
            {complete
              ? "Your agency is fully set up. The guide below is here whenever you need it."
              : "Each step you finish gets stamped. They tick themselves as you use the app."}
          </p>
        </div>
        <p className="tabular font-heading text-2xl" aria-live="polite">
          {loading ? "…" : `${done} of ${steps.length}`}
        </p>
      </div>
      <div className="h-2 overflow-hidden rounded-full bg-muted" role="progressbar" aria-label="Setup progress" aria-valuenow={percent} aria-valuemin={0} aria-valuemax={100}>
        <div className="help-progress h-full rounded-full bg-maize" style={{ width: loading ? "0%" : `${percent}%` }} />
      </div>
      <ul className="grid grid-cols-2 gap-3 sm:grid-cols-4">
        {steps.map((step, i) => {
          const Icon = step.icon;
          return (
            <li key={step.key}>
              <Link
                href={step.href}
                className={cn(
                  "group grid h-full justify-items-center gap-2 rounded-lg border px-2 py-3 text-center text-sm transition-colors",
                  step.done ? "border-primary/40 bg-primary/5" : "border-dashed hover:border-primary hover:bg-accent/50",
                )}
              >
                <span className="relative grid size-14 place-items-center">
                  <span className={cn("grid size-12 place-items-center rounded-full border-2 border-dashed", step.done ? "border-transparent" : "border-input text-muted-foreground group-hover:text-primary")}>
                    <Icon aria-hidden="true" className="size-5" />
                  </span>
                  {step.done && !loading && (
                    <span aria-hidden="true" className="help-stamp absolute inset-0 grid place-items-center rounded-full border-[3px] border-primary text-primary" style={{ animationDelay: `${150 + i * 110}ms` }}>
                      <Check className="size-7" strokeWidth={3} />
                    </span>
                  )}
                </span>
                <span className={cn(step.done && "text-muted-foreground")}>{step.label}</span>
                <span className="sr-only">{step.done ? "(done)" : "(to do)"}</span>
              </Link>
            </li>
          );
        })}
      </ul>
    </section>
  );
}
