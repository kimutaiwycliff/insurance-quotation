"use client";

import { useQueryClient } from "@tanstack/react-query";
import { CircleCheck, Plus, RefreshCw } from "lucide-react";
import Link from "next/link";
import { useState } from "react";
import { toast } from "sonner";

import { Field, FormError } from "@/components/forms/field";
import { todayIso } from "@/components/policies/new-policy";
import { expiryText, PolicyStatus, STAGE_LABELS } from "@/components/policies/status";
import { useCan } from "@/components/shell/me-context";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { NativeSelect } from "@/components/ui/native-select";
import { Skeleton } from "@/components/ui/skeleton";
import { Textarea } from "@/components/ui/textarea";
import { ifMatch } from "@/lib/api/fetcher";
import type { PaymentInMethod, PaymentOut, PolicyOut } from "@/lib/api/generated/model";
import {
  getPoliciesGetQueryKey,
  policiesActivate,
  policiesCancel,
  policiesMarkRemitted,
  policiesRecordPayment,
  policiesUpdate,
  policiesVoidPayment,
  usePoliciesGet,
} from "@/lib/api/generated/policies/policies";
import { formatDate, formatMoney, fractionToPercent } from "@/lib/format";
import { ApiError, problemMessage } from "@/lib/problem";

const METHOD_LABELS: Record<string, string> = { mpesa: "M-Pesa", bank: "Bank", card: "Card", cheque: "Cheque", cash: "Cash", other: "Other" };

function useAction(onDone: () => Promise<unknown>) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  async function run(fn: () => Promise<unknown>, success?: string): Promise<boolean> {
    setBusy(true);
    setError(null);
    try {
      await fn();
      await onDone();
      if (success) toast.success(success);
      return true;
    } catch (e) {
      setError(e instanceof ApiError ? problemMessage(e.problem) : "That did not work. Try again.");
      return false;
    } finally {
      setBusy(false);
    }
  }
  return { busy, error, setError, run };
}

function Activation({ policy, refresh }: { policy: PolicyOut; refresh: () => Promise<unknown> }) {
  const [confirmed, setConfirmed] = useState(false);
  const [exception, setException] = useState("");
  const [note, setNote] = useState("");
  const { busy, error, run } = useAction(refresh);
  const money = (a: string) => formatMoney(a, policy.currency);
  const paidInFull = Number(policy.balance) === 0;

  return (
    <section aria-labelledby="activation-heading" className="grid gap-3 rounded-lg border-l-[3px] border-maize bg-card p-4">
      <h2 id="activation-heading" className="text-xl">Awaiting cover</h2>
      <p className="max-w-prose text-muted-foreground">
        No premium, no cover: the insurer may only start cover once the premium is paid
        {policy.premium_exceptions.length > 0 ? ", unless one of the exceptions below applies" : ""}.{" "}
        {paidInFull ? `${money(policy.paid)} is recorded, the full premium.` : `${money(policy.paid)} of ${money(policy.total_premium)} is recorded.`}
      </p>
      <FormError message={error} />
      {!paidInFull && policy.premium_exceptions.length > 0 && (
        <Field label="Exception" optional>
          {(p) => (
            <NativeSelect {...p} value={exception} onChange={(e) => setException(e.target.value)}>
              <option value="">None: wait for full payment</option>
              {policy.premium_exceptions.map((e) => <option key={e.id} value={e.id}>{e.name}</option>)}
            </NativeSelect>
          )}
        </Field>
      )}
      {exception && <Field label="Note" optional hint="e.g. instalment plan agreed with the insurer">{(p) => <Input {...p} value={note} onChange={(e) => setNote(e.target.value)} />}</Field>}
      <label className="flex items-center gap-2">
        <input type="checkbox" className="size-4 accent-[var(--acacia)]" checked={confirmed} onChange={(e) => setConfirmed(e.target.checked)} />
        The insurer has confirmed cover
      </label>
      <div>
        <Button
          disabled={!confirmed || busy || (!paidInFull && !exception)}
          onClick={() => run(() => policiesActivate(policy.id, exception ? { basis: "exception", exception_id: exception, insurer_confirmed: true, note } : { insurer_confirmed: true }), "Policy is active")}
        >
          <CircleCheck aria-hidden="true" /> Mark as active
        </Button>
      </div>
    </section>
  );
}

function RecordPayment({ policy, open, onOpenChange, refresh }: { policy: PolicyOut; open: boolean; onOpenChange: (o: boolean) => void; refresh: () => Promise<unknown> }) {
  const [amount, setAmount] = useState("");
  const [paidOn, setPaidOn] = useState(todayIso());
  const [method, setMethod] = useState<PaymentInMethod>("mpesa");
  const [reference, setReference] = useState("");
  const [paidTo, setPaidTo] = useState<"insurer" | "agent">(policy.collection_mode === "agent_collected" ? "agent" : "insurer");
  const { busy, error, run } = useAction(refresh);
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Record a payment</DialogTitle>
          <DialogDescription>A record for your book. No money moves through this app.</DialogDescription>
        </DialogHeader>
        <div className="grid gap-4">
          <FormError message={error} />
          <Field label={`Amount (${policy.currency})`}>{(p) => <Input {...p} inputMode="decimal" value={amount || policy.balance} onChange={(e) => setAmount(e.target.value.replace(/[, ]/g, ""))} />}</Field>
          <div className="grid gap-4 sm:grid-cols-2">
            <Field label="Paid on">{(p) => <Input {...p} type="date" value={paidOn} onChange={(e) => setPaidOn(e.target.value)} />}</Field>
            <Field label="Method">
              {(p) => <NativeSelect {...p} value={method} onChange={(e) => setMethod(e.target.value as PaymentInMethod)}>{Object.entries(METHOD_LABELS).map(([v, l]) => <option key={v} value={v}>{l}</option>)}</NativeSelect>}
            </Field>
          </div>
          <Field label="Reference" optional hint="e.g. the M-Pesa code">{(p) => <Input {...p} value={reference} onChange={(e) => setReference(e.target.value)} />}</Field>
          <Field label="Paid to">
            {(p) => (
              <NativeSelect {...p} value={paidTo} onChange={(e) => setPaidTo(e.target.value as "insurer" | "agent")}>
                <option value="insurer">The insurer</option>
                <option value="agent">Me, to pass on to the insurer</option>
              </NativeSelect>
            )}
          </Field>
        </div>
        <DialogFooter>
          <Button
            disabled={busy}
            onClick={async () => {
              const ok = await run(() => policiesRecordPayment(policy.id, { amount: amount || policy.balance, paid_on: paidOn, method, reference: reference || undefined, paid_to: paidTo }), paidTo === "agent" ? "Payment recorded. Remit it to the insurer today." : "Payment recorded");
              if (ok) { setAmount(""); setReference(""); onOpenChange(false); }
            }}
          >
            Record payment
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

function PaymentRow({ policy, payment, canPay, refresh }: { policy: PolicyOut; payment: PaymentOut; canPay: boolean; refresh: () => Promise<unknown> }) {
  const { busy, error, run } = useAction(refresh);
  const [voiding, setVoiding] = useState(false);
  const [reason, setReason] = useState("");
  const voided = Boolean(payment.voided_at);
  const toRemit = payment.paid_to === "agent" && !payment.remitted_on && !voided;
  return (
    <tr className="border-b last:border-0">
      <td className="px-3 py-2">{formatDate(payment.paid_on)}</td>
      <td className={`tabular px-3 py-2 text-right ${voided ? "text-muted-foreground line-through" : ""}`}>{formatMoney(payment.amount, payment.currency)}</td>
      <td className="px-3 py-2">{METHOD_LABELS[payment.method] ?? payment.method}{payment.reference ? ` · ${payment.reference}` : ""}</td>
      <td className="px-3 py-2">
        {voided ? <span className="text-muted-foreground">Voided: {payment.void_reason}</span>
          : payment.paid_to === "insurer" ? "To the insurer"
          : payment.remitted_on ? `Remitted ${formatDate(payment.remitted_on)}`
          : <span className="font-bold text-destructive">Remit to the insurer today</span>}
      </td>
      <td className="px-3 py-2 text-right whitespace-nowrap">
        {canPay && toRemit && (
          <Button size="sm" variant="outline" disabled={busy} onClick={() => run(() => policiesMarkRemitted(policy.id, payment.id, { remitted_on: todayIso() }), "Marked as remitted")}>Remitted</Button>
        )}
        {canPay && !voided && (
          <Button size="sm" variant="ghost" disabled={busy} onClick={() => setVoiding(true)}>Void</Button>
        )}
        <Dialog open={voiding} onOpenChange={setVoiding}>
          <DialogContent>
            <DialogHeader>
              <DialogTitle>Void this payment</DialogTitle>
              <DialogDescription>{formatMoney(payment.amount, payment.currency)} on {formatDate(payment.paid_on)}. It stays in the history, crossed out.</DialogDescription>
            </DialogHeader>
            <FormError message={error} />
            <Textarea aria-label="Why void it" rows={2} value={reason} onChange={(e) => setReason(e.target.value)} placeholder="e.g. Entered on the wrong policy" />
            <DialogFooter>
              <Button variant="destructive" disabled={busy || reason.trim().length < 2} onClick={async () => { if (await run(() => policiesVoidPayment(policy.id, payment.id, { reason: reason.trim() }), "Payment voided")) setVoiding(false); }}>Void payment</Button>
            </DialogFooter>
          </DialogContent>
        </Dialog>
      </td>
    </tr>
  );
}

export function PolicyDetail({ policyId }: { policyId: string }) {
  const queryClient = useQueryClient();
  const policy = usePoliciesGet(policyId);
  const canWrite = useCan("client:write");
  const canPay = useCan("premium:write");
  const [paying, setPaying] = useState(false);
  const [editing, setEditing] = useState(false);
  const [number, setNumber] = useState<string | null>(null);
  const [cancelling, setCancelling] = useState(false);
  const [reason, setReason] = useState("");
  const refresh = () => queryClient.invalidateQueries({ queryKey: getPoliciesGetQueryKey(policyId) });
  const action = useAction(refresh);

  if (!policy.data) return <Skeleton className="h-96 w-full" />;
  const p = policy.data;
  const money = (a: string) => formatMoney(a, p.currency);
  const breakdown = p.breakdown as { lines?: { code: string; label: string; amount: string; charged_to: string }[] };

  return (
    <div className="grid gap-6">
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <h1 className="text-3xl">{p.description}</h1>
          <p className="mt-1 text-muted-foreground">
            <Link className="font-bold text-primary hover:underline" href={`/clients/${p.client.id}`}>{p.client.display_name}</Link> · {p.insurer_name}, {p.product_name}
            {p.policy_number ? ` · ${p.policy_number}` : ""}
          </p>
          <div className="mt-2"><PolicyStatus status={p.status} /></div>
        </div>
        <div className="flex flex-wrap gap-2">
          {canPay && p.status !== "cancelled" && <Button variant="outline" onClick={() => setPaying(true)}><Plus aria-hidden="true" /> Record payment</Button>}
          {canWrite && <Button variant="outline" onClick={() => { setNumber(p.policy_number ?? ""); setEditing(true); }}>Policy number</Button>}
          {canWrite && ["active", "expired"].includes(p.status) && !p.renewed_to_id && (
            <Button asChild><Link href={`/quotes/new?client=${p.client.id}&renew=${p.id}`}><RefreshCw aria-hidden="true" /> Renewal quote</Link></Button>
          )}
        </div>
      </div>

      <dl className="grid grid-cols-2 gap-x-8 gap-y-3 sm:grid-cols-4">
        <div><dt className="text-sm text-muted-foreground">Cover</dt><dd className="font-bold">{formatDate(p.start_date)} to {formatDate(p.end_date)}</dd></div>
        <div><dt className="text-sm text-muted-foreground">Expires</dt><dd className="font-bold">{expiryText(p.days_to_expiry)}</dd></div>
        <div><dt className="text-sm text-muted-foreground">Premium</dt><dd className="tabular font-bold">{money(p.total_premium)}</dd></div>
        <div><dt className="text-sm text-muted-foreground">Unpaid</dt><dd className={`tabular font-bold ${Number(p.balance) > 0 ? "text-destructive" : ""}`}>{money(p.balance)}</dd></div>
        {p.sum_insured && <div><dt className="text-sm text-muted-foreground">Sum insured</dt><dd className="tabular font-bold">{money(p.sum_insured)}</dd></div>}
        <div><dt className="text-sm text-muted-foreground">Premium paid</dt><dd className="font-bold">{p.collection_mode === "agent_collected" ? "Through you" : "Directly to the insurer"}</dd></div>
        <div><dt className="text-sm text-muted-foreground">Renewal</dt><dd className="font-bold">{STAGE_LABELS[p.renewal_stage]}{p.lost_reason ? `: ${p.lost_reason}` : ""}</dd></div>
        {p.details.map((d) => <div key={d.label}><dt className="text-sm text-muted-foreground">{d.label}</dt><dd className="font-bold">{d.value}</dd></div>)}
      </dl>

      {(p.renewed_from_id || p.renewed_to_id || p.quote_id || p.renewal_quote_id) && (
        <ul className="flex flex-wrap gap-x-6 gap-y-1 text-sm">
          {p.quote_id && <li><Link className="text-primary hover:underline" href={`/quotes/${p.quote_id}`}>Quote it came from</Link></li>}
          {p.renewed_from_id && <li><Link className="text-primary hover:underline" href={`/policies/${p.renewed_from_id}`}>Previous policy</Link></li>}
          {p.renewal_quote_id && <li><Link className="text-primary hover:underline" href={`/quotes/${p.renewal_quote_id}`}>Renewal quote</Link></li>}
          {p.renewed_to_id && <li><Link className="text-primary hover:underline" href={`/policies/${p.renewed_to_id}`}>Renewed policy</Link></li>}
        </ul>
      )}

      {p.status === "pending" && canWrite && <Activation policy={p} refresh={refresh} />}
      {p.activated_at && (
        <p className="text-sm text-muted-foreground">
          Active since {formatDate(p.activated_at)}{p.activation.basis === "exception" ? `, before full payment: ${String(p.activation.exception)} (${String(p.activation.source)})` : ", premium paid in full"}.
        </p>
      )}
      {Number(p.unremitted) > 0 && (
        <p className="rounded-md border border-destructive/40 px-3 py-2 font-bold text-destructive">
          {money(p.unremitted)} you received has not been passed on to {p.insurer_name}. Premium you collect must reach the insurer the same day.
        </p>
      )}

      <section aria-labelledby="payments-heading" className="grid gap-2">
        <h2 id="payments-heading" className="text-xl">Payments</h2>
        {p.payments.length === 0 ? (
          <p className="text-muted-foreground">No payments recorded.</p>
        ) : (
          <div className="overflow-x-auto rounded-lg border bg-card">
            <table className="w-full min-w-[36rem] text-sm">
              <caption className="sr-only">Payments</caption>
              <thead><tr className="border-b text-left text-muted-foreground"><th className="px-3 py-2 font-normal">Date</th><th className="px-3 py-2 text-right font-normal">Amount</th><th className="px-3 py-2 font-normal">Method</th><th className="px-3 py-2 font-normal">Status</th><th className="px-3 py-2"><span className="sr-only">Actions</span></th></tr></thead>
              <tbody>{p.payments.map((pay) => <PaymentRow key={pay.id} policy={p} payment={pay} canPay={canPay} refresh={refresh} />)}</tbody>
            </table>
          </div>
        )}
      </section>

      {breakdown.lines && breakdown.lines.length > 0 && (
        <section aria-labelledby="breakdown-heading" className="grid gap-2">
          <h2 id="breakdown-heading" className="text-xl">Premium breakdown</h2>
          <table className="w-full max-w-md text-sm">
            <tbody>
              {breakdown.lines.filter((l) => l.charged_to === "client").map((l) => (
                <tr key={l.code} className="border-b"><th scope="row" className="py-1.5 text-left font-normal">{l.label}</th><td className="tabular py-1.5 text-right">{money(l.amount)}</td></tr>
              ))}
            </tbody>
          </table>
          {p.commission && (
            <p className="text-sm text-muted-foreground">
              Expected commission {money(String(p.commission.gross))} ({fractionToPercent(String(p.commission.rate))}%), {money(String(p.commission.net))} after withholding tax.
            </p>
          )}
        </section>
      )}
      {p.notes && <p className="max-w-prose whitespace-pre-line text-muted-foreground">{p.notes}</p>}

      {canWrite && p.status !== "cancelled" && (
        <div><Button variant="ghost" className="text-destructive" onClick={() => setCancelling(true)}>Cancel policy</Button></div>
      )}

      <RecordPayment policy={p} open={paying} onOpenChange={setPaying} refresh={refresh} />

      <Dialog open={editing} onOpenChange={setEditing}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Insurer&apos;s policy number</DialogTitle>
            <DialogDescription>As printed on the insurer&apos;s schedule or certificate.</DialogDescription>
          </DialogHeader>
          <FormError message={action.error} />
          <Input aria-label="Policy number" value={number ?? ""} onChange={(e) => setNumber(e.target.value)} />
          <DialogFooter>
            <Button disabled={action.busy} onClick={async () => { if (await action.run(() => policiesUpdate(p.id, { policy_number: number || null }, ifMatch(p.version)), "Saved")) setEditing(false); }}>Save</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      <Dialog open={cancelling} onOpenChange={setCancelling}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Cancel this policy</DialogTitle>
            <DialogDescription>Record why. Refunds are handled with the insurer.</DialogDescription>
          </DialogHeader>
          <FormError message={action.error} />
          <Textarea aria-label="Reason" rows={3} value={reason} onChange={(e) => setReason(e.target.value)} placeholder="e.g. Client sold the car" />
          <DialogFooter>
            <Button variant="destructive" disabled={action.busy || reason.trim().length < 2} onClick={async () => { if (await action.run(() => policiesCancel(p.id, { reason: reason.trim() }), "Policy cancelled")) setCancelling(false); }}>Cancel policy</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
