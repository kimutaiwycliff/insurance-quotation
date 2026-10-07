"use client";

import { useRouter } from "next/navigation";
import { useTranslations } from "next-intl";
import { useState, type FormEvent } from "react";

import { Seal } from "@/components/brand/seal";
import { Field, FormError } from "@/components/forms/field";
import { BrandingEditor } from "@/components/settings/branding-editor";
import { OrganizationForm } from "@/components/settings/organization-form";
import { MeProvider } from "@/components/shell/me-context";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { authClient, bumpOrgEpoch } from "@/lib/auth-client";
import type { Me } from "@/lib/me";
import { cn } from "@/lib/utils";

type Step = "agency" | "details" | "brand";
const STEPS: Step[] = ["agency", "details", "brand"];

export function slugify(name: string): string {
  const base = name
    .toLowerCase()
    .normalize("NFKD")
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-|-$/g, "")
    .slice(0, 40);
  return `${base || "agency"}-${Math.random().toString(36).slice(2, 6)}`;
}

function Progress({ step }: { step: Step }) {
  const t = useTranslations("onboarding");
  const labels: Record<Step, string> = { agency: t("stepAgency"), details: t("stepDetails"), brand: t("stepBrand") };
  const index = STEPS.indexOf(step);
  return (
    <ol className="mb-8 flex gap-2" aria-label="Setup progress">
      {STEPS.map((s, i) => (
        <li key={s} className="flex-1" aria-current={s === step ? "step" : undefined}>
          <span className={cn("block h-1.5 rounded-full", i <= index ? "bg-maize" : "bg-border")} />
          <span className={cn("mt-2 block text-sm", s === step ? "font-bold" : "text-muted-foreground")}>
            {i + 1}. {labels[s]}
          </span>
        </li>
      ))}
    </ol>
  );
}

function AgencyStep({ onName }: { onName: (name: string) => void }) {
  const t = useTranslations("onboarding");
  const router = useRouter();
  const orgs = authClient.useListOrganizations();
  const [name, setName] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function create(event: FormEvent) {
    event.preventDefault();
    if (name.trim().length < 2) return setError("Enter your agency's name.");
    setBusy(true);
    const { data, error: failure } = await authClient.organization.create({ name: name.trim(), slug: slugify(name) });
    if (failure || !data) {
      setBusy(false);
      return setError(failure?.message ?? "The agency was not created. Try again.");
    }
    // Make it the session's active agency explicitly (tokens carry the active organization).
    await authClient.organization.setActive({ organizationId: data.id });
    bumpOrgEpoch();
    router.push("/onboarding?step=details");
    router.refresh();
  }

  async function continueWith(organizationId: string) {
    await authClient.organization.setActive({ organizationId });
    bumpOrgEpoch();
    router.replace("/");
    router.refresh();
  }

  return (
    <div className="grid gap-8">
      {(orgs.data?.length ?? 0) > 0 && (
        <section aria-labelledby="existing" className="grid gap-2">
          <h2 id="existing" className="text-lg">{t("pickExisting")}</h2>
          {orgs.data!.map((org) => (
            <button key={org.id} type="button" onClick={() => continueWith(org.id)} className="flex items-center gap-3 rounded-md border bg-card px-3 py-2 text-left font-bold hover:border-primary">
              <Seal name={org.name} size={32} className="text-primary" /> {org.name}
            </button>
          ))}
          <p className="mt-4 text-muted-foreground">{t("or")}</p>
        </section>
      )}
      <form onSubmit={create} className="grid gap-5" noValidate>
        <FormError message={error} />
        <Field label={t("agencyName")} hint={t("agencyNameHint")}>
          {(p) => (
            <Input
              {...p}
              value={name}
              onChange={(e) => {
                setName(e.target.value);
                onName(e.target.value);
              }}
              autoComplete="organization"
              autoFocus
              className="h-12 text-lg"
            />
          )}
        </Field>
        <Button type="submit" size="lg" disabled={busy}>{t("create")}</Button>
      </form>
    </div>
  );
}

export function OnboardingWizard({ step, me, userName }: { step: Step; me: Me | null; userName: string }) {
  const t = useTranslations("onboarding");
  const common = useTranslations("common");
  const router = useRouter();
  const [agencyName, setAgencyName] = useState(me?.tenant.name ?? "");

  const body =
    step === "agency" || !me ? (
      <AgencyStep onName={setAgencyName} />
    ) : (
      <MeProvider me={me}>
        {step === "details" ? (
          <>
            <p className="mb-6 max-w-prose text-muted-foreground">{t("detailsBody")}</p>
            <OrganizationForm compact onSaved={() => router.push("/onboarding?step=brand")} />
            <button type="button" className="mt-4 text-sm text-primary hover:underline" onClick={() => router.push("/onboarding?step=brand")}>
              {common("skip")}
            </button>
          </>
        ) : (
          <>
            <p className="mb-6 max-w-prose text-muted-foreground">{t("brandBody")}</p>
            <BrandingEditor submitLabel={t("finish")} onSaved={() => { router.replace("/"); router.refresh(); }} />
          </>
        )}
      </MeProvider>
    );

  return (
    <div className="grid min-h-dvh lg:grid-cols-[minmax(0,4fr)_minmax(0,7fr)]">
      <aside className="hidden bg-ink p-12 text-[#f6f7f4] lg:flex lg:flex-col lg:justify-between">
        <p className="font-heading text-xl font-bold">BrokerOS</p>
        <div>
          <Seal name={agencyName || "Your agency"} size={200} className="mb-8 transition-transform" />
          <p className="font-heading text-3xl leading-tight">{agencyName || `Karibu, ${userName.split(" ")[0]}.`}</p>
        </div>
        <span aria-hidden="true" className="h-1 w-24 bg-maize" />
      </aside>
      <main className="px-5 py-10 sm:px-10 lg:py-14">
        <div className={cn("mx-auto", step === "brand" ? "max-w-5xl" : "max-w-lg")}>
          <h1 className="mb-6 text-3xl">{t(step === "agency" ? "stepAgency" : step === "details" ? "stepDetails" : "stepBrand")}</h1>
          <Progress step={me ? step : "agency"} />
          {body}
        </div>
      </main>
    </div>
  );
}
