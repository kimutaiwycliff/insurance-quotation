"use client";

import { useRouter } from "next/navigation";
import { useState, type FormEvent } from "react";

import { Field, FormError } from "@/components/forms/field";
import { useCan } from "@/components/shell/me-context";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { NativeSelect } from "@/components/ui/native-select";
import { Skeleton } from "@/components/ui/skeleton";
import { Textarea } from "@/components/ui/textarea";
import { useClientsGet } from "@/lib/api/generated/clients/clients";
import { useJurisdictionPackGet, useProductsList } from "@/lib/api/generated/insurers/insurers";
import type {
  PaymentIn,
  PaymentInMethod,
  PolicyCreateCollectionMode,
} from "@/lib/api/generated/model";
import {
  policiesCreate,
  policiesFromQuote,
  usePoliciesGet,
} from "@/lib/api/generated/policies/policies";
import { useQuotesGet } from "@/lib/api/generated/quotes/quotes";
import { formatDate, formatMoney, percentToFraction } from "@/lib/format";
import { ApiError, problemMessage } from "@/lib/problem";

const METHODS: { value: PaymentInMethod; label: string }[] = [
  { value: "mpesa", label: "M-Pesa" },
  { value: "bank", label: "Bank transfer" },
  { value: "card", label: "Card" },
  { value: "cheque", label: "Cheque" },
  { value: "cash", label: "Cash" },
  { value: "other", label: "Other" },
];

/** Today's date in Nairobi as YYYY-MM-DD. */
export function todayIso(): string {
  return new Intl.DateTimeFormat("en-CA", { timeZone: "Africa/Nairobi" }).format(new Date());
}

function addDays(iso: string, days: number): string {
  const d = new Date(`${iso}T12:00:00Z`);
  d.setUTCDate(d.getUTCDate() + days);
  return d.toISOString().slice(0, 10);
}

function Cover({
  total,
  currency,
  state,
  set,
}: {
  total: string | null;
  currency: string;
  state: CoverState;
  set: (s: CoverState) => void;
}) {
  return (
    <>
      <div className="grid gap-4 sm:grid-cols-2">
        <Field label="Cover starts">
          {(p) => (
            <Input
              {...p}
              type="date"
              required
              value={state.start}
              onChange={(e) => set({ ...state, start: e.target.value })}
            />
          )}
        </Field>
        <Field label="Cover ends" optional hint="Leave empty for one year.">
          {(p) => (
            <Input
              {...p}
              type="date"
              value={state.end}
              onChange={(e) => set({ ...state, end: e.target.value })}
            />
          )}
        </Field>
      </div>
      <Field
        label="Insurer's policy number"
        optional
        hint="Add it later if the insurer has not issued it yet."
      >
        {(p) => (
          <Input
            {...p}
            value={state.number}
            onChange={(e) => set({ ...state, number: e.target.value })}
          />
        )}
      </Field>
      <fieldset className="grid gap-2">
        <legend className="mb-1 text-sm font-bold">Who receives the premium</legend>
        <label className="flex items-start gap-2">
          <input
            type="radio"
            name="mode"
            className="mt-1 size-4 accent-[var(--acacia)]"
            checked={state.mode === "insurer_direct"}
            onChange={() => set({ ...state, mode: "insurer_direct" })}
          />
          <span>The client pays the insurer directly</span>
        </label>
        <label className="flex items-start gap-2">
          <input
            type="radio"
            name="mode"
            className="mt-1 size-4 accent-[var(--acacia)]"
            checked={state.mode === "agent_collected"}
            onChange={() => set({ ...state, mode: "agent_collected" })}
          />
          <span>
            I collect it for the insurer{" "}
            <span className="text-muted-foreground block text-sm">
              Only if the insurer authorised you. You must pass it on the same day; we add a
              reminder task.
            </span>
          </span>
        </label>
      </fieldset>
      <label className="flex items-center gap-2 font-bold">
        <input
          type="checkbox"
          className="size-4 accent-[var(--acacia)]"
          checked={state.paid}
          onChange={(e) =>
            set({ ...state, paid: e.target.checked, amount: state.amount || total || "" })
          }
        />
        The premium has been paid
      </label>
      {state.paid && (
        <div className="bg-card grid gap-4 rounded-md border p-4 sm:grid-cols-2">
          <Field label={`Amount (${currency})`}>
            {(p) => (
              <Input
                {...p}
                inputMode="decimal"
                required
                value={state.amount}
                onChange={(e) => set({ ...state, amount: e.target.value.replace(/[, ]/g, "") })}
              />
            )}
          </Field>
          <Field label="Paid on">
            {(p) => (
              <Input
                {...p}
                type="date"
                required
                value={state.paidOn}
                onChange={(e) => set({ ...state, paidOn: e.target.value })}
              />
            )}
          </Field>
          <Field label="Method">
            {(p) => (
              <NativeSelect
                {...p}
                value={state.method}
                onChange={(e) => set({ ...state, method: e.target.value as PaymentInMethod })}
              >
                {METHODS.map((m) => (
                  <option key={m.value} value={m.value}>
                    {m.label}
                  </option>
                ))}
              </NativeSelect>
            )}
          </Field>
          <Field label="Reference" optional hint="e.g. the M-Pesa code">
            {(p) => (
              <Input
                {...p}
                value={state.reference}
                onChange={(e) => set({ ...state, reference: e.target.value })}
              />
            )}
          </Field>
        </div>
      )}
      <label className="flex items-start gap-2">
        <input
          type="checkbox"
          className="mt-1 size-4 accent-[var(--acacia)]"
          checked={state.confirmed}
          onChange={(e) => set({ ...state, confirmed: e.target.checked })}
        />
        <span>
          <span className="font-bold">The insurer has confirmed cover</span>
          <span className="text-muted-foreground block text-sm">
            With the premium paid in full, the policy becomes active straight away.
          </span>
        </span>
      </label>
      <Field label="Notes" optional>
        {(p) => (
          <Textarea
            {...p}
            rows={2}
            value={state.notes}
            onChange={(e) => set({ ...state, notes: e.target.value })}
          />
        )}
      </Field>
    </>
  );
}

interface CoverState {
  start: string;
  end: string;
  number: string;
  mode: PolicyCreateCollectionMode;
  paid: boolean;
  amount: string;
  paidOn: string;
  method: PaymentInMethod;
  reference: string;
  confirmed: boolean;
  notes: string;
}

function initialCover(start = todayIso()): CoverState {
  return {
    start,
    end: "",
    number: "",
    mode: "insurer_direct",
    paid: false,
    amount: "",
    paidOn: todayIso(),
    method: "mpesa",
    reference: "",
    confirmed: false,
    notes: "",
  };
}

function coverBody(s: CoverState) {
  const payment: PaymentIn | undefined =
    s.paid && s.amount
      ? {
          amount: s.amount,
          paid_on: s.paidOn,
          method: s.method,
          reference: s.reference || undefined,
        }
      : undefined;
  return {
    start_date: s.start,
    end_date: s.end || undefined,
    policy_number: s.number || undefined,
    collection_mode: s.mode,
    payment,
    insurer_confirmed: s.confirmed,
    notes: s.notes || undefined,
  };
}

function useSubmit() {
  const router = useRouter();
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  async function run(fn: () => Promise<{ id: string }>) {
    setBusy(true);
    setError(null);
    try {
      const policy = await fn();
      router.push(`/policies/${policy.id}`);
    } catch (e) {
      setError(
        e instanceof ApiError ? problemMessage(e.problem) : "The policy was not saved. Try again.",
      );
      setBusy(false);
    }
  }
  return { error, busy, run };
}

export function PolicyFromQuote({ quoteId }: { quoteId: string }) {
  const quote = useQuotesGet(quoteId);
  const [option, setOption] = useState<number | null>(null);
  const [cover, setCover] = useState(initialCover);
  const { error, busy, run } = useSubmit();
  if (!quote.data) return <Skeleton className="h-96 w-full" />;
  const q = quote.data;
  const chosen = q.accepted_position ?? option;
  const picked = q.option_list.find((o) => o.position === chosen);

  function submit(event: FormEvent) {
    event.preventDefault();
    void run(() =>
      policiesFromQuote({
        quote_id: quoteId,
        option: q.accepted_position ? undefined : (chosen ?? undefined),
        ...coverBody(cover),
      }),
    );
  }

  return (
    <form onSubmit={submit} className="grid max-w-2xl gap-6">
      <div>
        <h1 className="text-3xl">New policy</h1>
        <p className="text-muted-foreground mt-1">
          From {q.number ?? q.title} for {q.client.display_name}
        </p>
      </div>
      <FormError message={error} />
      {q.accepted_position ? (
        <p className="border-primary bg-accent rounded-md border px-3 py-2">
          The client accepted option {q.accepted_position}: <strong>{picked?.insurer_name}</strong>,{" "}
          {picked && formatMoney(picked.client_total, q.currency)}.
        </p>
      ) : (
        <fieldset className="grid gap-2">
          <legend className="mb-1 text-sm font-bold">Which option did the client accept?</legend>
          {q.option_list.map((o) => (
            <label
              key={o.position}
              className="bg-card flex items-center gap-3 rounded-md border px-3 py-2"
            >
              <input
                type="radio"
                name="option"
                required
                className="size-4 accent-[var(--acacia)]"
                checked={option === o.position}
                onChange={() => {
                  setOption(o.position);
                  setCover({ ...cover, amount: o.client_total });
                }}
              />
              <span className="flex-1">
                {o.position}. {o.insurer_name}{" "}
                <span className="text-muted-foreground">{o.product_name}</span>
              </span>
              <span className="tabular">{formatMoney(o.client_total, q.currency)}</span>
            </label>
          ))}
        </fieldset>
      )}
      <Cover
        total={picked?.client_total ?? null}
        currency={q.currency}
        state={cover}
        set={setCover}
      />
      <div>
        <Button type="submit" size="lg" disabled={busy || !chosen}>
          Save policy
        </Button>
      </div>
    </form>
  );
}

export function NewPolicy({ clientId, renewalOf }: { clientId: string; renewalOf?: string }) {
  const client = useClientsGet(clientId);
  const pack = useJurisdictionPackGet();
  const products = useProductsList();
  const previous = usePoliciesGet(renewalOf ?? "", { query: { enabled: Boolean(renewalOf) } });
  const [productId, setProductId] = useState("");
  const [insurer, setInsurer] = useState("");
  const [classCode, setClassCode] = useState("");
  const [description, setDescription] = useState("");
  const [premium, setPremium] = useState("");
  const [sumInsured, setSumInsured] = useState("");
  const seesOwnCommission = useCan("commission:read:own");
  const seesAllCommission = useCan("commission:read:all");
  const [rate, setRate] = useState("");
  const [base, setBase] = useState("");
  const [cover, setCover] = useState<CoverState | null>(null);
  const { error, busy, run } = useSubmit();

  const prev = renewalOf ? previous.data : undefined;
  if (!client.data || !pack.data || !products.data || (renewalOf && !prev))
    return <Skeleton className="h-96 w-full" />;
  const state = cover ?? initialCover(prev ? addDays(prev.end_date, 1) : todayIso());
  const currency =
    products.data.find((p) => p.id === productId)?.currency ?? prev?.currency ?? "KES";
  const currentClass = classCode || prev?.class_code || pack.data.classes[0]?.code || "";
  const currentInsurer = insurer || (prev && !productId ? prev.insurer_name : "");
  const currentDescription = description || prev?.description || "";

  function submit(event: FormEvent) {
    event.preventDefault();
    void run(() =>
      policiesCreate({
        client_id: clientId,
        product_id: productId || undefined,
        insurer_name: productId ? undefined : currentInsurer,
        class_code: productId ? undefined : currentClass,
        description: currentDescription || undefined,
        details: prev?.details,
        total_premium: premium,
        sum_insured: sumInsured || undefined,
        renewed_from_id: renewalOf,
        commission_rate: rate ? (percentToFraction(rate) ?? undefined) : undefined,
        commission_base: base || undefined,
        ...coverBody(state),
      }),
    );
  }

  return (
    <form onSubmit={submit} className="grid max-w-2xl gap-6">
      <div>
        <h1 className="text-3xl">{prev ? "Record renewal" : "Add a policy"}</h1>
        <p className="text-muted-foreground mt-1">
          For {client.data.display_name}
          {prev
            ? `: renews ${prev.description} (${prev.insurer_name}, ends ${formatDate(prev.end_date)})`
            : ""}
        </p>
      </div>
      <FormError message={error} />
      <Field
        label="Product"
        optional
        hint="Choose one of your products, or type the insurer below."
      >
        {(p) => (
          <NativeSelect {...p} value={productId} onChange={(e) => setProductId(e.target.value)}>
            <option value="">Another insurer or product</option>
            {products.data.map((product) => (
              <option key={product.id} value={product.id}>
                {product.name}
              </option>
            ))}
          </NativeSelect>
        )}
      </Field>
      {!productId && (
        <div className="grid gap-4 sm:grid-cols-2">
          <Field label="Insurer">
            {(p) => (
              <Input
                {...p}
                required
                value={currentInsurer}
                onChange={(e) => setInsurer(e.target.value)}
              />
            )}
          </Field>
          <Field label="Class of business">
            {(p) => (
              <NativeSelect
                {...p}
                value={currentClass}
                onChange={(e) => setClassCode(e.target.value)}
              >
                {pack.data.classes.map((c) => (
                  <option key={c.code} value={c.code}>
                    {c.name}
                  </option>
                ))}
              </NativeSelect>
            )}
          </Field>
        </div>
      )}
      <Field label="What is covered" hint="e.g. KDA 123A Toyota Axio, or Family medical: 4 members">
        {(p) => (
          <Input
            {...p}
            required
            value={currentDescription}
            onChange={(e) => setDescription(e.target.value)}
          />
        )}
      </Field>
      <div className="grid gap-4 sm:grid-cols-2">
        <Field label={`Total premium (${currency})`} hint="What the client pays, levies included.">
          {(p) => (
            <Input
              {...p}
              inputMode="decimal"
              required
              value={premium}
              onChange={(e) => setPremium(e.target.value.replace(/[, ]/g, ""))}
            />
          )}
        </Field>
        <Field label="Sum insured" optional>
          {(p) => (
            <Input
              {...p}
              inputMode="decimal"
              value={sumInsured}
              onChange={(e) => setSumInsured(e.target.value.replace(/[, ]/g, ""))}
            />
          )}
        </Field>
      </div>
      {(seesOwnCommission || seesAllCommission) && (
        <div className="grid gap-4 sm:grid-cols-2">
          <Field
            label="Commission rate (%)"
            optional
            hint={productId ? "Leave empty to use the product's rate." : undefined}
          >
            {(p) => (
              <Input
                {...p}
                inputMode="decimal"
                value={rate}
                onChange={(e) => setRate(e.target.value)}
              />
            )}
          </Field>
          <Field
            label={`Premium before levies (${currency})`}
            optional
            hint="Commission is paid on this amount."
          >
            {(p) => (
              <Input
                {...p}
                inputMode="decimal"
                value={base}
                onChange={(e) => setBase(e.target.value.replace(/[, ]/g, ""))}
              />
            )}
          </Field>
        </div>
      )}
      <Cover total={premium || null} currency={currency} state={state} set={setCover} />
      <div>
        <Button type="submit" size="lg" disabled={busy}>
          Save policy
        </Button>
      </div>
    </form>
  );
}
