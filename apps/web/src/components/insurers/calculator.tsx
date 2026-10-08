"use client";

import { useMutation } from "@tanstack/react-query";
import { useMemo, useState, type FormEvent } from "react";

import { PackBanner } from "@/components/insurers/pack-banner";
import { Field, FormError } from "@/components/forms/field";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { NativeSelect } from "@/components/ui/native-select";
import { premiumCompare, useJurisdictionPackGet, useProductsList } from "@/lib/api/generated/insurers/insurers";
import type { CalculationOut, CompareIn } from "@/lib/api/generated/model";
import { formatMoney, fractionToPercent } from "@/lib/format";
import { ApiError, problemMessage } from "@/lib/problem";
import { cn } from "@/lib/utils";

function Result({ result, cheapest }: { result: CalculationOut; cheapest: boolean }) {
  const [open, setOpen] = useState(cheapest);
  const money = (amount: string) => formatMoney(amount, result.currency);
  const client = result.lines.filter((l) => l.charged_to === "client");
  return (
    <li className={cn("rounded-lg border bg-card", cheapest && "border-primary ring-2 ring-primary/15")}>
      <button type="button" onClick={() => setOpen(!open)} aria-expanded={open} className="flex w-full flex-wrap items-baseline gap-x-4 gap-y-1 px-4 py-3 text-left">
        <span className="min-w-0 flex-1">
          <span className="block font-bold">{result.product.insurer_name}</span>
          <span className="text-sm text-muted-foreground">{result.product.name}</span>
        </span>
        {cheapest && <span className="rounded-full bg-maize px-2 py-0.5 text-xs font-bold text-ink">Lowest</span>}
        <span className="tabular font-heading text-2xl">{money(result.client_total)}</span>
      </button>
      {open && (
        <div className="grid gap-3 border-t px-4 py-3">
          <table className="w-full text-sm">
            <caption className="sr-only">Premium breakdown</caption>
            <tbody>
              {client.map((line) => (
                <tr key={line.code} className="border-b last:border-0">
                  <th scope="row" className="py-1.5 text-left font-normal">
                    {line.label}
                    {line.source && <span className="block text-xs text-muted-foreground">{line.source}</span>}
                  </th>
                  <td className="tabular py-1.5 text-right">{money(line.amount)}</td>
                </tr>
              ))}
              <tr>
                <th scope="row" className="pt-2 text-left">Total payable by the client</th>
                <td className="tabular pt-2 text-right font-bold">{money(result.client_total)}</td>
              </tr>
            </tbody>
          </table>
          {result.product.excess_text && <p className="text-sm"><strong>Excess:</strong> {result.product.excess_text}</p>}
          {result.commission && (
            <p className="rounded-md bg-muted px-3 py-2 text-sm">
              Your commission: {money(result.commission.gross)} ({fractionToPercent(result.commission.rate)}%), withholding tax {money(result.commission.wht)}, you receive <strong>{money(result.commission.net)}</strong>.
            </p>
          )}
          {result.notes.map((note) => <p key={note} className="text-sm text-muted-foreground">{note}</p>)}
        </div>
      )}
    </li>
  );
}

export function PremiumCalculator() {
  const pack = useJurisdictionPackGet();
  const products = useProductsList();
  const [classCode, setClassCode] = useState<string | null>(null);
  const [excluded, setExcluded] = useState<Set<string>>(new Set());
  const [sumInsured, setSumInsured] = useState("");
  const [members, setMembers] = useState<Record<string, string>>({});
  const [benefits, setBenefits] = useState<Set<string>>(new Set());
  const [coverNote, setCoverNote] = useState(false);
  const [stampDuty, setStampDuty] = useState("");

  const available = useMemo(() => new Set((products.data ?? []).map((p) => p.class_code)), [products.data]);
  const classes = (pack.data?.classes ?? []).filter((c) => available.has(c.code));
  const current = classCode ?? classes[0]?.code ?? null;
  const ofClass = (products.data ?? []).filter((p) => p.class_code === current);
  const chosen = ofClass.filter((p) => !excluded.has(p.id));
  const needsSum = chosen.some((p) => p.rating_basis === "rate_on_sum_insured" || p.benefits.some((b) => b.basis === "rate_on_sum_insured"));
  const tierLabels = [...new Set(chosen.flatMap((p) => p.member_tiers.map((t) => t.label)))];
  const optional = [...new Map(chosen.flatMap((p) => p.benefits.filter((b) => b.optional !== false).map((b) => [b.code, b.name] as const))).entries()];

  const compare = useMutation({
    mutationFn: (body: CompareIn) => premiumCompare(body),
    onError: () => undefined,
  });
  const needsStamp = compare.data?.results.some((r) => r.needs_input.includes("stamp_duty")) ?? false;

  function submit(event: FormEvent) {
    event.preventDefault();
    compare.mutate({
      product_ids: chosen.map((p) => p.id),
      sum_insured: needsSum ? sumInsured || undefined : undefined,
      members: tierLabels.filter((l) => Number(members[l] ?? 0) > 0).map((label) => ({ label, count: Number(members[label]) })),
      benefit_codes: [...benefits],
      document_kind: coverNote ? "cover_note" : "policy",
      stamp_duty_manual: stampDuty || undefined,
    });
  }

  if (pack.data && products.data && classes.length === 0) {
    return <p className="text-muted-foreground">Add insurers and products in Settings → Insurers &amp; products to start pricing.</p>;
  }

  return (
    <div className="grid gap-6 lg:grid-cols-[minmax(0,22rem)_minmax(0,1fr)]">
      <form onSubmit={submit} className="grid content-start gap-5">
        <PackBanner />
        <Field label="Class of business">
          {(p) => (
            <NativeSelect {...p} value={current ?? ""} onChange={(e) => { setClassCode(e.target.value); setBenefits(new Set()); compare.reset(); }}>
              {classes.map((c) => <option key={c.code} value={c.code}>{c.name}</option>)}
            </NativeSelect>
          )}
        </Field>
        <fieldset className="grid gap-1.5">
          <legend className="mb-1 text-sm font-bold">Compare</legend>
          {ofClass.map((p) => (
            <label key={p.id} className="flex items-center gap-2">
              <input type="checkbox" className="size-4 accent-[var(--acacia)]" checked={!excluded.has(p.id)}
                onChange={(e) => { const next = new Set(excluded); if (e.target.checked) next.delete(p.id); else next.add(p.id); setExcluded(next); }} />
              {p.name}
            </label>
          ))}
        </fieldset>
        {needsSum && <Field label="Sum insured" hint="e.g. the vehicle's value">{(p) => <Input {...p} inputMode="decimal" required value={sumInsured} onChange={(e) => setSumInsured(e.target.value.replace(/[, ]/g, ""))} />}</Field>}
        {tierLabels.length > 0 && (
          <fieldset className="grid grid-cols-3 gap-2">
            <legend className="mb-1 text-sm font-bold">Members</legend>
            {tierLabels.map((label) => (
              <label key={label} className="grid gap-1 text-sm">{label}
                <Input type="number" min={0} max={50} value={members[label] ?? (label === tierLabels[0] ? "1" : "0")} onChange={(e) => setMembers({ ...members, [label]: e.target.value })} />
              </label>
            ))}
          </fieldset>
        )}
        {optional.length > 0 && (
          <fieldset className="grid gap-1.5">
            <legend className="mb-1 text-sm font-bold">Benefits</legend>
            {optional.map(([code, name]) => (
              <label key={code} className="flex items-center gap-2">
                <input type="checkbox" className="size-4 accent-[var(--acacia)]" checked={benefits.has(code)}
                  onChange={(e) => { const next = new Set(benefits); if (e.target.checked) next.add(code); else next.delete(code); setBenefits(next); }} />
                {name}
              </label>
            ))}
          </fieldset>
        )}
        <label className="flex items-center gap-2 text-sm">
          <input type="checkbox" className="size-4 accent-[var(--acacia)]" checked={coverNote} onChange={(e) => setCoverNote(e.target.checked)} />
          Cover note (not stamped)
        </label>
        {needsStamp && <Field label="Stamp duty" hint="From the insurer's quote (marine and travel bands are not built in yet).">{(p) => <Input {...p} inputMode="decimal" value={stampDuty} onChange={(e) => setStampDuty(e.target.value)} />}</Field>}
        <Button type="submit" size="lg" disabled={chosen.length === 0 || compare.isPending}>{chosen.length > 1 ? `Compare ${chosen.length} quotes` : "Calculate"}</Button>
      </form>
      <section aria-label="Results" aria-live="polite" className="grid content-start gap-3">
        {compare.error && <FormError message={compare.error instanceof ApiError ? problemMessage(compare.error.problem) : "The premium could not be calculated."} />}
        {(compare.data?.errors ?? []).map((e) => <FormError key={e.product_id} message={`${e.product}: ${e.error}`} />)}
        {compare.data && (
          <ol className="grid gap-3">
            {compare.data.results.map((r, i) => <Result key={r.product.id} result={r} cheapest={i === 0 && compare.data.results.length > 1} />)}
          </ol>
        )}
        {!compare.data && !compare.error && <p className="rounded-lg border border-dashed px-4 py-10 text-center text-muted-foreground">Enter the risk details and compare insurers side by side.</p>}
      </section>
    </div>
  );
}
