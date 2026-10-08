"use client";

import { Plus, Trash2 } from "lucide-react";
import { useRouter } from "next/navigation";
import { useMemo, useState, type FormEvent } from "react";

import { PackBanner } from "@/components/insurers/pack-banner";
import { Field, FormError } from "@/components/forms/field";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { NativeSelect } from "@/components/ui/native-select";
import { Skeleton } from "@/components/ui/skeleton";
import { Textarea } from "@/components/ui/textarea";
import { useClientsGet } from "@/lib/api/generated/clients/clients";
import { useJurisdictionPackGet, useProductsList } from "@/lib/api/generated/insurers/insurers";
import { useOrganizationGet } from "@/lib/api/generated/organization/organization";
import type { PolicyOut } from "@/lib/api/generated/model";
import { policiesRenewalQuote, usePoliciesGet } from "@/lib/api/generated/policies/policies";
import { quotesCreate } from "@/lib/api/generated/quotes/quotes";
import { formatDate } from "@/lib/format";
import { ApiError, problemMessage } from "@/lib/problem";

export function NewQuote({ clientId, renewalOf }: { clientId: string; renewalOf?: string }) {
  const previous = usePoliciesGet(renewalOf ?? "", { query: { enabled: Boolean(renewalOf) } });
  if (renewalOf && !previous.data) return <Skeleton className="h-96 w-full" />;
  return <QuoteForm clientId={clientId} renewal={renewalOf ? previous.data : undefined} />;
}

function QuoteForm({ clientId, renewal }: { clientId: string; renewal?: PolicyOut }) {
  const router = useRouter();
  const client = useClientsGet(clientId);
  const pack = useJurisdictionPackGet();
  const products = useProductsList();
  const org = useOrganizationGet();
  const [classCode, setClassCode] = useState<string | null>(renewal?.class_code ?? null);
  const [chosen, setChosen] = useState<Set<string>>(new Set());
  const [recommended, setRecommended] = useState<string | null>(null);
  const [sumInsured, setSumInsured] = useState(renewal?.sum_insured ? renewal.sum_insured.replace(/\.0+$/, "") : "");
  const [members, setMembers] = useState<Record<string, string>>({});
  const [benefits, setBenefits] = useState<Set<string>>(new Set());
  const [details, setDetails] = useState(renewal?.details.length ? renewal.details : [{ label: "Vehicle", value: "" }]);
  const [notes, setNotes] = useState("");
  const [validDays, setValidDays] = useState("30");
  const [stampDuty, setStampDuty] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const available = useMemo(() => new Set((products.data ?? []).map((p) => p.class_code)), [products.data]);
  const classes = (pack.data?.classes ?? []).filter((c) => available.has(c.code));
  const current = classCode ?? classes[0]?.code ?? null;
  const ofClass = (products.data ?? []).filter((p) => p.class_code === current);
  const selected = ofClass.filter((p) => chosen.has(p.id));
  const multi = org.data?.multi_insurer_quotes ?? true;
  const needsSum = selected.some((p) => p.rating_basis === "rate_on_sum_insured" || p.benefits.some((b) => b.basis === "rate_on_sum_insured"));
  const tierLabels = [...new Set(selected.flatMap((p) => p.member_tiers.map((t) => t.label)))];
  const optional = [...new Map(selected.flatMap((p) => p.benefits.filter((b) => b.optional !== false).map((b) => [b.code, b.name] as const))).entries()];
  const manualStamp = current === "marine_cargo" || current === "travel";

  function toggle(id: string, on: boolean) {
    const next = multi ? new Set(chosen) : new Set<string>();
    if (on) next.add(id); else next.delete(id);
    setChosen(next);
  }

  async function submit(event: FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError(null);
    try {
      const body = {
        product_ids: selected.map((p) => p.id),
        recommended_product_id: recommended && chosen.has(recommended) ? recommended : undefined,
        risk: {
          sum_insured: needsSum ? sumInsured : undefined,
          members: tierLabels.filter((l) => Number(members[l] ?? (l === tierLabels[0] ? 1 : 0)) > 0).map((label) => ({ label, count: Number(members[label] ?? 1) })),
          benefit_codes: [...benefits],
          stamp_duty_manual: manualStamp && stampDuty ? stampDuty : undefined,
        },
        details: details.filter((d) => d.label && d.value),
        notes: notes || undefined,
        valid_days: Number(validDays) || 30,
      };
      const quote = renewal ? await policiesRenewalQuote(renewal.id, body) : await quotesCreate({ client_id: clientId, ...body });
      router.push(`/quotes/${quote.id}`);
    } catch (e) {
      setError(e instanceof ApiError ? problemMessage(e.problem) : "The quote was not created. Try again.");
      setBusy(false);
    }
  }

  if (!client.data || !pack.data || !products.data) return <Skeleton className="h-96 w-full" />;
  return (
    <form onSubmit={submit} className="grid max-w-2xl gap-6">
      <div>
        <h1 className="text-3xl">{renewal ? "Renewal quote" : "New quote"}</h1>
        <p className="mt-1 text-muted-foreground">
          For {client.data.display_name}{renewal ? `: ${renewal.description}, now with ${renewal.insurer_name} until ${formatDate(renewal.end_date)}` : ""}
        </p>
      </div>
      <PackBanner />
      <FormError message={error} />
      <Field label="Class of business">
        {(p) => (
          <NativeSelect {...p} value={current ?? ""} onChange={(e) => { setClassCode(e.target.value); setChosen(new Set()); setBenefits(new Set()); }}>
            {classes.map((c) => <option key={c.code} value={c.code}>{c.name}</option>)}
          </NativeSelect>
        )}
      </Field>
      <fieldset className="grid gap-2">
        <legend className="mb-1 text-sm font-bold">{multi ? "Insurers to compare" : "Insurer"}</legend>
        {ofClass.map((p) => (
          <div key={p.id} className="flex flex-wrap items-center gap-3 rounded-md border bg-card px-3 py-2">
            <label className="flex flex-1 items-center gap-2">
              <input type={multi ? "checkbox" : "radio"} name="product" className="size-4 accent-[var(--acacia)]" checked={chosen.has(p.id)} onChange={(e) => toggle(p.id, e.target.checked)} />
              {p.name}
            </label>
            {multi && chosen.has(p.id) && (
              <label className="flex items-center gap-1.5 text-sm">
                <input type="radio" name="recommended" className="size-4 accent-[var(--acacia)]" checked={recommended === p.id} onChange={() => setRecommended(p.id)} />
                Recommend
              </label>
            )}
          </div>
        ))}
      </fieldset>
      {needsSum && <Field label="Sum insured">{(p) => <Input {...p} inputMode="decimal" required value={sumInsured} onChange={(e) => setSumInsured(e.target.value.replace(/[, ]/g, ""))} />}</Field>}
      {tierLabels.length > 0 && (
        <fieldset className="grid grid-cols-3 gap-2">
          <legend className="mb-1 text-sm font-bold">Members</legend>
          {tierLabels.map((label, i) => (
            <label key={label} className="grid gap-1 text-sm">{label}
              <Input type="number" min={0} max={50} value={members[label] ?? (i === 0 ? "1" : "0")} onChange={(e) => setMembers({ ...members, [label]: e.target.value })} />
            </label>
          ))}
        </fieldset>
      )}
      {optional.length > 0 && (
        <fieldset className="grid gap-1.5">
          <legend className="mb-1 text-sm font-bold">Benefits</legend>
          {optional.map(([code, name]) => (
            <label key={code} className="flex items-center gap-2">
              <input type="checkbox" className="size-4 accent-[var(--acacia)]" checked={benefits.has(code)} onChange={(e) => { const n = new Set(benefits); if (e.target.checked) n.add(code); else n.delete(code); setBenefits(n); }} />
              {name}
            </label>
          ))}
        </fieldset>
      )}
      {manualStamp && <Field label="Stamp duty" hint="From the insurer's quote.">{(p) => <Input {...p} inputMode="decimal" value={stampDuty} onChange={(e) => setStampDuty(e.target.value)} />}</Field>}
      <fieldset className="grid gap-2">
        <legend className="mb-1 text-sm font-bold">Details shown on the quote</legend>
        {details.map((d, i) => (
          <div key={i} className="grid grid-cols-[9rem_minmax(0,1fr)_auto] gap-2">
            <Input aria-label="Detail" value={d.label} onChange={(e) => setDetails(details.map((x, j) => (j === i ? { ...x, label: e.target.value } : x)))} />
            <Input aria-label={d.label || "Value"} value={d.value} placeholder="e.g. KDA 123A, Toyota Axio 2019" onChange={(e) => setDetails(details.map((x, j) => (j === i ? { ...x, value: e.target.value } : x)))} />
            <Button type="button" variant="ghost" size="icon" aria-label="Remove detail" onClick={() => setDetails(details.filter((_, j) => j !== i))}><Trash2 /></Button>
          </div>
        ))}
        <Button type="button" variant="outline" size="sm" className="justify-self-start" onClick={() => setDetails([...details, { label: "", value: "" }])}><Plus /> Add detail</Button>
      </fieldset>
      <Field label="Note to the client" optional>{(p) => <Textarea {...p} rows={3} value={notes} onChange={(e) => setNotes(e.target.value)} />}</Field>
      <Field label="Valid for (days)">{(p) => <Input {...p} type="number" min={1} max={90} className="w-28" value={validDays} onChange={(e) => setValidDays(e.target.value)} />}</Field>
      <div><Button type="submit" size="lg" disabled={busy || selected.length === 0}>Create quote</Button></div>
    </form>
  );
}
