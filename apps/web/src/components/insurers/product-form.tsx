"use client";

import { Plus, Trash2 } from "lucide-react";
import { useState, type FormEvent } from "react";

import { Field, FormError } from "@/components/forms/field";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { NativeSelect } from "@/components/ui/native-select";
import { Textarea } from "@/components/ui/textarea";
import type { InsuranceClassOut, ProductBenefitInput as ProductBenefit, ProductIn, ProductOut } from "@/lib/api/generated/model";
import { fractionToPercent, percentToFraction } from "@/lib/format";
import { ApiError, problemMessage } from "@/lib/problem";

type Basis = ProductIn["rating_basis"];
interface BenefitRow { name: string; basis: ProductBenefit["basis"]; value: string; optional: boolean; selected_by_default: boolean }
interface TierRow { label: string; amount: string }

const slug = (name: string) => name.toLowerCase().replace(/[^a-z0-9]+/g, "_").replace(/^_|_$/g, "").slice(0, 40) || "benefit";

export function ProductForm({
  classes,
  initial,
  showCommission,
  onSubmit,
}: {
  classes: InsuranceClassOut[];
  initial?: ProductOut;
  showCommission: boolean;
  onSubmit: (body: Omit<ProductIn, "insurer_id">) => Promise<void>;
}) {
  const [classCode, setClassCode] = useState(initial?.class_code ?? "motor_private");
  const [name, setName] = useState(initial?.name ?? "");
  const [basis, setBasis] = useState<Basis>((initial?.rating_basis as Basis) ?? "rate_on_sum_insured");
  const [rate, setRate] = useState(fractionToPercent(initial?.rate));
  const [flat, setFlat] = useState(initial?.flat_premium ?? "");
  const [minimum, setMinimum] = useState(initial?.min_premium ? String(Number(initial.min_premium)) : "");
  const [excess, setExcess] = useState(initial?.excess_text ?? "");
  const [commNew, setCommNew] = useState(fractionToPercent(initial?.commission_rate_new));
  const [commRenewal, setCommRenewal] = useState(fractionToPercent(initial?.commission_rate_renewal));
  const [tiers, setTiers] = useState<TierRow[]>(initial?.member_tiers.map((t) => ({ label: t.label, amount: String(Number(t.amount)) })) ?? [{ label: "Principal", amount: "" }]);
  const [benefits, setBenefits] = useState<BenefitRow[]>(
    initial?.benefits.map((b) => ({ name: b.name, basis: b.basis, value: b.basis === "flat" ? String(b.value) : fractionToPercent(String(b.value)), optional: b.optional ?? true, selected_by_default: b.selected_by_default ?? false })) ?? [],
  );
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function submit(event: FormEvent) {
    event.preventDefault();
    setError(null);
    const pct = (label: string, value: string) => {
      if (!value) return undefined;
      const f = percentToFraction(value);
      if (f === null) throw new Error(`${label}: enter a percentage like 4 or 3.5`);
      return f;
    };
    try {
      const body: Omit<ProductIn, "insurer_id"> = {
        class_code: classCode,
        name,
        rating_basis: basis,
        rate: basis === "rate_on_sum_insured" ? pct("Rate", rate) : undefined,
        flat_premium: basis === "flat" ? flat || undefined : undefined,
        min_premium: minimum || "0",
        member_tiers: basis === "per_member" ? tiers.filter((t) => t.label && t.amount) : [],
        benefits: benefits.filter((b) => b.name && b.value).map((b) => ({
          code: slug(b.name), name: b.name, basis: b.basis,
          value: b.basis === "flat" ? b.value : pct(b.name, b.value)!, optional: b.optional, selected_by_default: b.selected_by_default,
        })),
        excess_text: excess || undefined,
        ...(showCommission ? { commission_rate_new: pct("Commission (new)", commNew), commission_rate_renewal: pct("Commission (renewal)", commRenewal) } : {}),
      };
      setBusy(true);
      await onSubmit(body);
    } catch (e) {
      setError(e instanceof ApiError ? problemMessage(e.problem) + (e.problem.errors?.[0] ? ` (${e.problem.errors[0].message})` : "") : (e as Error).message);
    } finally {
      setBusy(false);
    }
  }

  const setBenefit = (i: number, patch: Partial<BenefitRow>) => setBenefits(benefits.map((b, j) => (j === i ? { ...b, ...patch } : b)));

  return (
    <form onSubmit={submit} className="grid gap-5">
      <FormError message={error} />
      <Field label="Class of business">
        {(p) => (
          <NativeSelect {...p} value={classCode} onChange={(e) => setClassCode(e.target.value)}>
            {classes.map((c) => <option key={c.code} value={c.code}>{c.name}</option>)}
          </NativeSelect>
        )}
      </Field>
      <Field label="Product name">{(p) => <Input {...p} required value={name} onChange={(e) => setName(e.target.value)} placeholder="e.g. Motor private comprehensive" />}</Field>
      <Field label="How it is priced">
        {(p) => (
          <NativeSelect {...p} value={basis} onChange={(e) => setBasis(e.target.value as Basis)}>
            <option value="rate_on_sum_insured">Rate on the sum insured</option>
            <option value="flat">Fixed premium</option>
            <option value="per_member">Per member (medical)</option>
            <option value="manual">Entered per quote</option>
          </NativeSelect>
        )}
      </Field>
      {basis === "rate_on_sum_insured" && (
        <Field label="Rate (%)" hint="e.g. 4 for 4% of the sum insured">{(p) => <Input {...p} inputMode="decimal" value={rate} onChange={(e) => setRate(e.target.value)} />}</Field>
      )}
      {basis === "flat" && <Field label="Premium">{(p) => <Input {...p} inputMode="decimal" value={flat} onChange={(e) => setFlat(e.target.value)} />}</Field>}
      {basis === "per_member" && (
        <fieldset className="grid gap-2">
          <legend className="mb-1 text-sm font-bold">Premium per member</legend>
          {tiers.map((tier, i) => (
            <div key={i} className="grid grid-cols-[minmax(0,1fr)_8rem_auto] gap-2">
              <Input aria-label="Member type" value={tier.label} onChange={(e) => setTiers(tiers.map((t, j) => (j === i ? { ...t, label: e.target.value } : t)))} />
              <Input aria-label={`Premium for ${tier.label || "member"}`} inputMode="decimal" value={tier.amount} onChange={(e) => setTiers(tiers.map((t, j) => (j === i ? { ...t, amount: e.target.value } : t)))} />
              <Button type="button" variant="ghost" size="icon" aria-label="Remove member type" onClick={() => setTiers(tiers.filter((_, j) => j !== i))}><Trash2 /></Button>
            </div>
          ))}
          <Button type="button" variant="outline" size="sm" className="justify-self-start" onClick={() => setTiers([...tiers, { label: "", amount: "" }])}><Plus /> Add member type</Button>
        </fieldset>
      )}
      <Field label="Minimum premium" optional>{(p) => <Input {...p} inputMode="decimal" value={minimum} onChange={(e) => setMinimum(e.target.value)} />}</Field>
      <fieldset className="grid gap-2">
        <legend className="mb-1 text-sm font-bold">Benefits and extensions</legend>
        {benefits.map((b, i) => (
          <div key={i} className="grid gap-2 rounded-md border p-2 sm:grid-cols-[minmax(0,1fr)_9rem_6rem_auto]">
            <Input aria-label="Benefit name" placeholder="e.g. Excess protector" value={b.name} onChange={(e) => setBenefit(i, { name: e.target.value })} />
            <NativeSelect aria-label="Benefit pricing" value={b.basis} onChange={(e) => setBenefit(i, { basis: e.target.value as BenefitRow["basis"] })}>
              <option value="rate_on_sum_insured">% of sum insured</option>
              <option value="rate_on_premium">% of premium</option>
              <option value="flat">Fixed amount</option>
            </NativeSelect>
            <Input aria-label={b.basis === "flat" ? "Amount" : "Percent"} inputMode="decimal" value={b.value} onChange={(e) => setBenefit(i, { value: e.target.value })} />
            <Button type="button" variant="ghost" size="icon" aria-label="Remove benefit" onClick={() => setBenefits(benefits.filter((_, j) => j !== i))}><Trash2 /></Button>
            <label className="flex items-center gap-2 text-sm sm:col-span-4">
              <input type="checkbox" className="size-4 accent-[var(--acacia)]" checked={b.selected_by_default} onChange={(e) => setBenefit(i, { selected_by_default: e.target.checked })} />
              Include by default
            </label>
          </div>
        ))}
        <Button type="button" variant="outline" size="sm" className="justify-self-start" onClick={() => setBenefits([...benefits, { name: "", basis: "rate_on_sum_insured", value: "", optional: true, selected_by_default: false }])}><Plus /> Add benefit</Button>
      </fieldset>
      <Field label="Excess" optional>{(p) => <Textarea {...p} rows={2} value={excess} onChange={(e) => setExcess(e.target.value)} placeholder="e.g. 2.5% of the claim, minimum KES 15,000" />}</Field>
      {showCommission && (
        <div className="grid grid-cols-2 gap-4">
          <Field label="Commission, new (%)" optional>{(p) => <Input {...p} inputMode="decimal" value={commNew} onChange={(e) => setCommNew(e.target.value)} />}</Field>
          <Field label="Commission, renewal (%)" optional>{(p) => <Input {...p} inputMode="decimal" value={commRenewal} onChange={(e) => setCommRenewal(e.target.value)} />}</Field>
        </div>
      )}
      <div><Button type="submit" size="lg" disabled={busy}>Save product</Button></div>
    </form>
  );
}
