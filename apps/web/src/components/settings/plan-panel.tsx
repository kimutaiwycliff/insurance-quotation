"use client";

import { useQueryClient } from "@tanstack/react-query";
import { Check, Smartphone } from "lucide-react";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { toast } from "sonner";

import { Field, FormError } from "@/components/forms/field";
import { useCan } from "@/components/shell/me-context";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Skeleton } from "@/components/ui/skeleton";
import type { CheckoutCycle, CheckoutPlan, PlanOut, SubscriptionOut, SubscriptionPaymentOut } from "@/lib/api/generated/model";
import {
  getSubscriptionGetQueryKey,
  getSubscriptionPaymentsListQueryKey,
  subscriptionCheckout,
  subscriptionPaymentGet,
  useSubscriptionGet,
  useSubscriptionPaymentsList,
  useSubscriptionPlans,
} from "@/lib/api/generated/subscription/subscription";
import { daysUntil, formatDate, formatMoney } from "@/lib/format";
import { ApiError, problemMessage } from "@/lib/problem";
import { cn } from "@/lib/utils";

const FEATURES: Record<string, string> = {
  insurance: "Quotes, policies and renewals",
  comparison_quotes: "Compare insurers on one quote",
  commission: "Commission tracking",
  book_import: "Import your book from Excel",
  client_reminders: "Reminders emailed to clients",
  branding: "Your logo and colours on documents",
  etims: "KRA eTIMS details on invoices",
  team: "Team members and roles",
};

const STATUS: Record<string, { label: string; tone: "default" | "secondary" | "destructive" | "outline" }> = {
  trialing: { label: "Free trial", tone: "secondary" },
  active: { label: "Active", tone: "default" },
  past_due: { label: "Payment due", tone: "destructive" },
  read_only: { label: "Read-only", tone: "destructive" },
  free: { label: "Free plan", tone: "outline" },
};

const DONE = new Set(["paid", "cancelled", "failed", "expired"]);
const kes = (amount: string) => formatMoney(amount, "KES");

function Meter({ label, used, limit }: { label: string; used: number; limit: number | undefined }) {
  const full = limit !== undefined && used >= limit;
  return (
    <div className="grid gap-1.5">
      <div className="flex justify-between gap-2 text-sm">
        <span>{label}</span>
        <span className={cn("tabular", full && "font-bold text-destructive")}>
          {used}
          {limit !== undefined ? ` of ${limit}` : ""}
        </span>
      </div>
      {limit !== undefined && (
        <div className="h-1.5 overflow-hidden rounded-full bg-muted" aria-hidden="true">
          <div className={cn("h-full rounded-full", full ? "bg-destructive" : "bg-primary")} style={{ width: `${Math.min(100, Math.round((used / limit) * 100))}%` }} />
        </div>
      )}
    </div>
  );
}

function Summary({ sub }: { sub: SubscriptionOut }) {
  const status = STATUS[sub.status] ?? { label: sub.status, tone: "outline" as const };
  let line: string;
  if (sub.status === "trialing" && sub.trial_ends_at) {
    const days = daysUntil(sub.trial_ends_at);
    line = `You have every Agency feature until ${formatDate(sub.trial_ends_at)} (${days} ${days === 1 ? "day" : "days"} left). After that you move to ${sub.paid_plan === "free" ? "the Free plan" : "your paid plan"} unless you choose a plan.`;
  } else if (sub.status === "active" && sub.period_end) {
    line = `Paid until ${formatDate(sub.period_end)}. Pay again before then to keep going; nothing is charged automatically.`;
  } else if (sub.status === "past_due" && sub.period_end) {
    line = `Your plan ended on ${formatDate(sub.period_end)}. Everything still works for a few days; pay now to avoid read-only mode.`;
  } else if (sub.status === "read_only") {
    line = "Your plan has lapsed. You can still see and download everything, but you cannot add or change anything until you pay.";
  } else {
    line = "The Free plan has no time limit. Upgrade when you need more.";
  }
  return (
    <section aria-labelledby="current-plan" className="grid gap-4 rounded-lg border bg-card p-4 sm:p-5">
      <div className="flex flex-wrap items-center gap-2">
        <h2 id="current-plan" className="text-xl">{sub.plan_name}</h2>
        <Badge variant={status.tone}>{status.label}</Badge>
        {sub.founding_member && <Badge variant="outline">Founding member: {sub.discount_percent}% off{sub.discount_until ? ` until ${formatDate(sub.discount_until)}` : ""}</Badge>}
      </div>
      <p className="max-w-prose text-muted-foreground">{line}</p>
      <div className="grid gap-4 sm:grid-cols-3">
        <Meter label="Clients" used={sub.usage.clients} limit={sub.limits.clients} />
        <Meter label="Documents issued this month" used={sub.usage.documents_this_month} limit={sub.limits.documents_per_month} />
        <Meter label="Team seats" used={sub.usage.seats_used} limit={sub.seats} />
      </div>
    </section>
  );
}

function PlanCard({ plan, cycle, current, onChoose, canPay }: { plan: PlanOut; cycle: CheckoutCycle; current: boolean; onChoose: () => void; canPay: boolean }) {
  const price = plan.prices.find((p) => p.cycle === cycle);
  const free = !price || Number(price.list_price) === 0;
  const discounted = price && price.price !== price.list_price;
  return (
    <li className={cn("flex flex-col gap-4 rounded-lg border bg-card p-4", current && "border-primary ring-1 ring-primary")}>
      <div className="grid gap-1">
        <h3 className="flex items-center gap-2 text-lg">
          {plan.name}
          {current && <Badge variant="secondary">Your plan</Badge>}
        </h3>
        <p className="text-sm text-muted-foreground">{plan.tagline}</p>
      </div>
      <div className="grid gap-0.5">
        {free ? (
          <span className="font-heading text-3xl">KES 0</span>
        ) : (
          <>
            <span className="tabular font-heading text-3xl">
              {kes(price.price)}
              <span className="text-base font-normal text-muted-foreground"> / {cycle === "yearly" ? "year" : "month"}</span>
            </span>
            {discounted && <span className="tabular text-sm text-muted-foreground"><s>{kes(price.list_price)}</s> founding price, first 12 months</span>}
            {plan.included_seats > 1 && (
              <span className="text-sm text-muted-foreground">
                {plan.included_seats} users included{plan.extra_seat_monthly ? `, then ${kes(plan.extra_seat_monthly)} per extra user a month` : ""}
              </span>
            )}
          </>
        )}
      </div>
      <ul className="grid flex-1 content-start gap-1.5 text-sm">
        {plan.features.map((f) => (
          <li key={f} className="flex gap-2">
            <Check className="mt-0.5 size-4 shrink-0 text-primary" aria-hidden="true" />
            {FEATURES[f] ?? f}
          </li>
        ))}
        {plan.limits.clients !== undefined && <li className="text-muted-foreground">Up to {plan.limits.clients} clients</li>}
        {plan.limits.documents_per_month !== undefined && <li className="text-muted-foreground">Up to {plan.limits.documents_per_month} documents a month</li>}
      </ul>
      {!free && canPay && (
        <Button variant={current ? "default" : "outline"} onClick={onChoose}>
          {current ? "Pay for this plan" : `Choose ${plan.name}`}
        </Button>
      )}
    </li>
  );
}

function CheckoutDialog({ plan, cycle, open, onOpenChange, onPaid }: { plan: PlanOut | null; cycle: CheckoutCycle; open: boolean; onOpenChange: (open: boolean) => void; onPaid: () => Promise<unknown> }) {
  const [phone, setPhone] = useState("");
  const [extra, setExtra] = useState(0);
  const [payment, setPayment] = useState<SubscriptionPaymentOut | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    if (!payment || DONE.has(payment.status)) return;
    const timer = window.setTimeout(async () => {
      try {
        const next = await subscriptionPaymentGet(payment.id);
        setPayment(next);
        if (next.status === "paid") {
          toast.success(`Payment received${next.receipt ? `: ${next.receipt}` : ""}. Your plan is active.`);
          await onPaid();
        }
      } catch {
        setPayment({ ...payment }); // try again on the next tick
      }
    }, 3000);
    return () => window.clearTimeout(timer);
  }, [payment, onPaid]);

  if (!plan) return null;
  const price = plan.prices.find((p) => p.cycle === cycle);
  const months = cycle === "yearly" ? 10 : 1; // yearly: 12 months for the price of 10
  const seatCost = plan.extra_seat_monthly ? Number(plan.extra_seat_monthly) * extra * months : 0;
  // Whole shillings only: plan prices and seat prices are whole numbers, so this is display arithmetic.
  const total = price ? String(Number(price.price) + seatCost) : "0";

  async function pay() {
    if (!plan) return;
    setBusy(true);
    setError(null);
    try {
      setPayment(await subscriptionCheckout({ plan: plan.code as CheckoutPlan, cycle, phone, extra_seats: extra || undefined }));
    } catch (e) {
      setError(e instanceof ApiError ? problemMessage(e.problem) : "The prompt was not sent. Try again.");
    } finally {
      setBusy(false);
    }
  }

  const text: Record<string, string> = {
    pending: "Check your phone and enter your M-Pesa PIN…",
    paid: "Paid. Thank you! Your plan is active.",
    cancelled: "The prompt was cancelled.",
    expired: "The prompt timed out. Try again.",
  };
  return (
    <Dialog open={open} onOpenChange={(o) => { onOpenChange(o); if (!o) { setPayment(null); setError(null); } }}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Pay for {plan.name} by M-Pesa</DialogTitle>
          <DialogDescription>
            We send a payment prompt to your phone. {cycle === "yearly" ? "A year" : "A month"} of {plan.name} costs {kes(total)}. Card payments are coming soon.
          </DialogDescription>
        </DialogHeader>
        <FormError message={error} />
        {payment ? (
          <p role="status" aria-live="polite" className={payment.status === "paid" ? "font-bold text-primary" : DONE.has(payment.status) ? "font-bold text-destructive" : ""}>
            {text[payment.status] ?? payment.result_desc ?? "The payment did not go through."}
            {payment.receipt && ` Receipt ${payment.receipt}.`}
          </p>
        ) : (
          <div className="grid gap-4">
            <Field label="Your M-Pesa number">{(p) => <Input {...p} type="tel" inputMode="tel" autoComplete="tel" value={phone} onChange={(e) => setPhone(e.target.value)} placeholder="0712 345 678" />}</Field>
            {plan.extra_seat_monthly && (
              <Field label={`Extra users beyond ${plan.included_seats}`} hint={`${kes(plan.extra_seat_monthly)} each a month`}>
                {(p) => <Input {...p} type="number" min={0} max={100} value={extra} onChange={(e) => setExtra(Math.max(0, Math.min(100, Number(e.target.value) || 0)))} />}
              </Field>
            )}
          </div>
        )}
        <DialogFooter>
          {!payment || DONE.has(payment.status) ? (
            payment?.status === "paid" ? (
              <Button onClick={() => onOpenChange(false)}>Done</Button>
            ) : (
              <Button disabled={busy || phone.trim().length < 9} onClick={() => { setPayment(null); void pay(); }}>
                <Smartphone aria-hidden="true" /> {payment ? "Send again" : `Send prompt for ${kes(total)}`}
              </Button>
            )
          ) : (
            <Button variant="ghost" onClick={() => onOpenChange(false)}>Close (it keeps going)</Button>
          )}
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

function History({ payments }: { payments: SubscriptionPaymentOut[] }) {
  if (!payments.length) return null;
  return (
    <section aria-labelledby="payments-heading" className="grid gap-3">
      <h2 id="payments-heading" className="text-xl">Payments</h2>
      <div className="overflow-x-auto rounded-lg border">
        <table className="w-full text-sm">
          <thead className="bg-muted/50 text-left">
            <tr>
              <th scope="col" className="px-3 py-2 font-bold">Date</th>
              <th scope="col" className="px-3 py-2 font-bold">Plan</th>
              <th scope="col" className="px-3 py-2 font-bold">Period</th>
              <th scope="col" className="px-3 py-2 text-right font-bold">Amount</th>
              <th scope="col" className="px-3 py-2 font-bold">M-Pesa receipt</th>
            </tr>
          </thead>
          <tbody>
            {payments.map((p) => (
              <tr key={p.id} className="border-t">
                <td className="px-3 py-2 whitespace-nowrap">{formatDate(p.created_at)}</td>
                <td className="px-3 py-2 capitalize">{p.plan}, {p.billing_cycle}</td>
                <td className="px-3 py-2 whitespace-nowrap">{p.period_start && p.period_end ? `${formatDate(p.period_start)} to ${formatDate(p.period_end)}` : "—"}</td>
                <td className="tabular px-3 py-2 text-right">{kes(p.amount)}</td>
                <td className="px-3 py-2">{p.status === "paid" ? <span className="font-mono">{p.receipt}</span> : <Badge variant={p.status === "pending" ? "secondary" : "outline"} className="capitalize">{p.status}</Badge>}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  );
}

export function PlanPanel() {
  const router = useRouter();
  const queryClient = useQueryClient();
  const canPay = useCan("org:update");
  const sub = useSubscriptionGet();
  const plans = useSubscriptionPlans();
  const payments = useSubscriptionPaymentsList();
  const [cycle, setCycle] = useState<CheckoutCycle>("monthly");
  const [chosen, setChosen] = useState<PlanOut | null>(null);
  const [open, setOpen] = useState(false);

  async function onPaid() {
    await Promise.all([
      queryClient.invalidateQueries({ queryKey: getSubscriptionGetQueryKey() }),
      queryClient.invalidateQueries({ queryKey: getSubscriptionPaymentsListQueryKey() }),
    ]);
    router.refresh(); // the shell's plan, features and banners come from /me on the server
  }

  if (!sub.data || !plans.data) {
    return (
      <div className="grid gap-4">
        <Skeleton className="h-40" />
        <Skeleton className="h-72" />
      </div>
    );
  }
  const current = sub.data.status === "trialing" ? (sub.data.paid_plan === "free" ? null : sub.data.paid_plan) : sub.data.plan;
  return (
    <div className="grid gap-8">
      <Summary sub={sub.data} />
      <section aria-labelledby="plans-heading" className="grid gap-4">
        <div className="flex flex-wrap items-end justify-between gap-3">
          <div className="grid gap-1">
            <h2 id="plans-heading" className="text-xl">Plans</h2>
            {sub.data.founding_places_left > 0 && !sub.data.founding_member && (
              <p className="max-w-prose text-sm text-muted-foreground">
                Founding offer: half price for your first 12 months. {sub.data.founding_places_left} of the first 100 places are left.
              </p>
            )}
          </div>
          <div role="radiogroup" aria-label="Billing cycle" className="inline-flex rounded-md border p-0.5">
            {(["monthly", "yearly"] as const).map((c) => (
              <button
                key={c}
                type="button"
                role="radio"
                aria-checked={cycle === c}
                onClick={() => setCycle(c)}
                className={cn("rounded px-3 py-1.5 text-sm", cycle === c ? "bg-primary font-bold text-primary-foreground" : "hover:bg-accent")}
              >
                {c === "monthly" ? "Monthly" : "Yearly (2 months free)"}
              </button>
            ))}
          </div>
        </div>
        <ul className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
          {plans.data.map((plan) => (
            <PlanCard
              key={plan.code}
              plan={plan}
              cycle={cycle}
              current={plan.code === current}
              canPay={canPay}
              onChoose={() => { setChosen(plan); setOpen(true); }}
            />
          ))}
        </ul>
        {!canPay && <p className="text-sm text-muted-foreground">Only the owner or an admin can pay for the plan.</p>}
      </section>
      <History payments={payments.data ?? []} />
      <CheckoutDialog plan={chosen} cycle={cycle} open={open} onOpenChange={setOpen} onPaid={onPaid} />
    </div>
  );
}
