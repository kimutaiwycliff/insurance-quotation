"use client";

import { Download } from "lucide-react";
import { useEffect, useState, type FormEvent } from "react";

import { Button } from "@/components/ui/button";
import { PublicPay } from "@/components/public/public-pay";
import { Input } from "@/components/ui/input";
import type { PublicLinkView } from "@/lib/api/generated/model";
import { formatMoney } from "@/lib/format";
import { cn } from "@/lib/utils";

const STATE_TEXT: Record<string, string> = {
  accepted: "You accepted this quotation. Thank you, we will be in touch.",
  paid: "This invoice is paid. Thank you.",
  declined: "You declined this quotation.",
  expired: "This quotation has expired. Ask your agent for an updated one.",
};

export function PublicActions({ token, view }: { token: string; view: PublicLinkView }) {
  const all = view.choices ?? [];
  const isSalesQuote = view.kind === "sales_quote";
  const choices = all.filter((c) => c.kind !== "addon");
  const addons = all.filter((c) => c.kind === "addon");
  const [chosen, setChosen] = useState<number[]>([]);
  const [state, setState] = useState(view.state ?? null);
  const [option, setOption] = useState<number | null>(choices.find((c) => c.recommended)?.position ?? choices[0]?.position ?? null);
  const [name, setName] = useState("");
  const [phone, setPhone] = useState("");
  const [agree, setAgree] = useState(false);
  const [declining, setDeclining] = useState(false);
  const [reason, setReason] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  // A view counts only when the page really rendered (not link previews): one beacon, with time on page.
  useEffect(() => {
    const started = Date.now();
    const send = () => {
      const body = new Blob([JSON.stringify({ duration_ms: Date.now() - started })], { type: "application/json" });
      navigator.sendBeacon(`/public-api/links/${token}/beacon`, body);
    };
    const onHide = () => { if (document.visibilityState === "hidden") send(); };
    const timer = window.setTimeout(send, 3000);
    document.addEventListener("visibilitychange", onHide, { once: true });
    return () => { window.clearTimeout(timer); document.removeEventListener("visibilitychange", onHide); };
  }, [token]);

  async function post(action: "accept" | "decline", body: object) {
    setBusy(true);
    setError(null);
    const response = await fetch(`/public-api/links/${token}/${action}`, {
      method: "POST", headers: { "content-type": "application/json" }, body: JSON.stringify(body),
    });
    setBusy(false);
    if (response.ok) setState(((await response.json()) as { state: string }).state);
    else setError(response.status === 409 ? "This quotation can no longer be answered." : "That did not go through. Check the form and try again.");
  }

  function accept(event: FormEvent) {
    event.preventDefault();
    void post(
      "accept",
      isSalesQuote
        ? { name, phone: phone || undefined, agree_terms: agree, addons: chosen }
        : { option, name, phone: phone || undefined, agree_terms: agree },
    );
  }

  const canAnswer = view.scopes.includes("accept") && state === "sent" && (isSalesQuote || choices.length > 0);
  return (
    <div className="grid gap-4">
      {view.has_download && (
        <div><Button asChild variant="outline"><a href={`/public-api/links/${token}/download`}><Download aria-hidden="true" /> Download PDF</a></Button></div>
      )}
      {state && STATE_TEXT[state] && <p role="status" className="rounded-md border border-primary bg-accent px-3 py-2 font-bold">{STATE_TEXT[state]}</p>}
      {view.payment && state !== "paid" && <PublicPay token={token} offer={view.payment} onPaid={() => setState("paid")} />}
      {canAnswer && !declining && (
        <form onSubmit={accept} className="grid gap-4 rounded-lg border bg-card p-4">
          {addons.length > 0 && (
            <fieldset className="grid gap-2">
              <legend className="mb-1 font-bold">Add any extras you want</legend>
              {addons.map((c) => (
                <label key={c.position} className={cn("flex items-center gap-3 rounded-md border px-3 py-2", chosen.includes(c.position) && "border-primary bg-accent")}>
                  <input type="checkbox" className="size-4 accent-[var(--acacia)]" checked={chosen.includes(c.position)} onChange={(e) => setChosen(e.target.checked ? [...chosen, c.position] : chosen.filter((p) => p !== c.position))} />
                  <span className="flex-1">{c.label}</span>
                  <span className="tabular font-bold">+ {formatMoney(c.amount, c.currency)}</span>
                </label>
              ))}
            </fieldset>
          )}
          {!isSalesQuote && <fieldset className="grid gap-2">
            <legend className="mb-1 font-bold">Choose an option</legend>
            {choices.map((c) => (
              <label key={c.position} className={cn("flex items-center gap-3 rounded-md border px-3 py-2", option === c.position && "border-primary bg-accent")}>
                <input type="radio" name="option" className="size-4 accent-[var(--acacia)]" checked={option === c.position} onChange={() => setOption(c.position)} />
                <span className="flex-1">{c.label}{c.recommended && <span className="ml-2 text-sm text-muted-foreground">(recommended)</span>}</span>
                <span className="tabular font-bold">{formatMoney(c.amount, c.currency)}</span>
              </label>
            ))}
          </fieldset>}
          <div className="grid gap-3 sm:grid-cols-2">
            <label className="grid gap-1.5 text-sm font-bold">Your full name<Input required value={name} onChange={(e) => setName(e.target.value)} autoComplete="name" /></label>
            <label className="grid gap-1.5 text-sm font-bold">Phone<Input type="tel" value={phone} onChange={(e) => setPhone(e.target.value)} autoComplete="tel" /></label>
          </div>
          <label className="flex items-start gap-2 text-sm">
            <input type="checkbox" required className="mt-1 size-4 accent-[var(--acacia)]" checked={agree} onChange={(e) => setAgree(e.target.checked)} />
            {isSalesQuote ? "I accept this quotation and its terms." : "I accept this option and the terms in the quotation."}
          </label>
          {error && <p role="alert" className="text-sm font-bold text-destructive">{error}</p>}
          <div className="flex flex-wrap gap-2">
            <Button type="submit" size="lg" disabled={busy || !agree || !name.trim() || (!isSalesQuote && option === null)}>{isSalesQuote ? "Accept quotation" : `Accept option ${option}`}</Button>
            <Button type="button" variant="ghost" onClick={() => setDeclining(true)}>Decline</Button>
          </div>
        </form>
      )}
      {canAnswer && declining && (
        <div className="grid gap-3 rounded-lg border bg-card p-4">
          <label className="grid gap-1.5 text-sm font-bold">Tell your agent why (optional)<Input value={reason} onChange={(e) => setReason(e.target.value)} /></label>
          <div className="flex gap-2">
            <Button variant="destructive" disabled={busy} onClick={() => post("decline", { reason })}>Decline quotation</Button>
            <Button variant="ghost" onClick={() => setDeclining(false)}>Back</Button>
          </div>
        </div>
      )}
    </div>
  );
}
