"use client";

import { CreditCard, Smartphone } from "lucide-react";
import { useEffect, useState, type FormEvent } from "react";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import type { PaymentOfferOut } from "@/lib/api/generated/model";
import { formatMoney } from "@/lib/format";

interface Attempt {
  attempt_id: string;
  status: string;
  message: string;
}

const DONE = new Set(["paid", "cancelled", "failed", "expired"]);

/** Pay an invoice from its link: an M-Pesa prompt to the client's phone (cards are coming soon). */
export function PublicPay({ token, offer, onPaid }: { token: string; offer: PaymentOfferOut; onPaid: () => void }) {
  const [phone, setPhone] = useState("");
  const [attempt, setAttempt] = useState<Attempt | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    if (!attempt || DONE.has(attempt.status)) return;
    const timer = window.setTimeout(async () => {
      const response = await fetch(`/public-api/links/${token}/pay/${attempt.attempt_id}`, { cache: "no-store" });
      if (!response.ok) return;
      const next = (await response.json()) as Attempt;
      setAttempt(next);
      if (next.status === "paid") onPaid();
    }, 3000);
    return () => window.clearTimeout(timer);
  }, [attempt, token, onPaid]);

  async function pay(event: FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError(null);
    const response = await fetch(`/public-api/links/${token}/pay`, {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ phone }),
    });
    setBusy(false);
    if (response.ok) setAttempt((await response.json()) as Attempt);
    else {
      const problem = (await response.json().catch(() => ({}))) as { detail?: string; title?: string };
      setError(problem.detail ?? problem.title ?? "The payment prompt was not sent. Try again.");
    }
  }

  const waiting = attempt && !DONE.has(attempt.status);
  return (
    <section aria-labelledby="pay-heading" className="grid gap-3 rounded-lg border bg-card p-4">
      <h2 id="pay-heading" className="text-xl">Pay {formatMoney(offer.amount, offer.currency)}</h2>
      {attempt?.status === "paid" ? (
        <p role="status" className="font-bold text-primary">{attempt.message}</p>
      ) : (
        <form onSubmit={pay} className="grid gap-3">
          <label className="grid gap-1.5 text-sm font-bold">
            Your M-Pesa number
            <Input type="tel" inputMode="tel" autoComplete="tel" required placeholder="0712 345 678" value={phone} onChange={(e) => setPhone(e.target.value)} disabled={Boolean(waiting)} />
          </label>
          {attempt && <p role="status" aria-live="polite" className={DONE.has(attempt.status) ? "font-bold text-destructive" : ""}>{attempt.message}</p>}
          {error && <p role="alert" className="text-sm font-bold text-destructive">{error}</p>}
          <div className="flex flex-wrap gap-2">
            <Button type="submit" size="lg" disabled={busy || Boolean(waiting) || !phone.trim()}>
              <Smartphone aria-hidden="true" /> {waiting ? "Check your phone…" : attempt ? "Try again" : "Pay with M-Pesa"}
            </Button>
            <Button type="button" size="lg" variant="outline" disabled aria-describedby="cards-soon">
              <CreditCard aria-hidden="true" /> Card
            </Button>
            <span id="cards-soon" className="self-center text-sm text-muted-foreground">Card payments coming soon</span>
          </div>
        </form>
      )}
    </section>
  );
}
