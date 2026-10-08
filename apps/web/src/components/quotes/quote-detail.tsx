"use client";

import { useQueryClient } from "@tanstack/react-query";
import { Copy, FileDown, MessageCircle, Send, ShieldCheck } from "lucide-react";
import Link from "next/link";
import { useState } from "react";
import { toast } from "sonner";

import { QuoteStatus } from "@/components/quotes/status";
import { Field, FormError } from "@/components/forms/field";
import { useCan } from "@/components/shell/me-context";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Skeleton } from "@/components/ui/skeleton";
import { Textarea } from "@/components/ui/textarea";
import type { Sent } from "@/lib/api/generated/model";
import { getQuotesGetQueryKey, quotesPdf, quotesSend, quotesWithdraw, useQuotesGet } from "@/lib/api/generated/quotes/quotes";
import { formatDate, formatMoney, fractionToPercent } from "@/lib/format";
import { ApiError, problemMessage } from "@/lib/problem";
import { cn } from "@/lib/utils";

interface Breakdown { lines: { code: string; label: string; kind: string; amount: string; charged_to: string }[]; notes: string[] }

export function QuoteDetail({ quoteId }: { quoteId: string }) {
  const queryClient = useQueryClient();
  const quote = useQuotesGet(quoteId);
  const canWrite = useCan("client:write");
  const [sending, setSending] = useState(false);
  const [email, setEmail] = useState<string | null>(null);
  const [message, setMessage] = useState("");
  const [sent, setSent] = useState<Sent | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  if (!quote.data) return <Skeleton className="h-96 w-full" />;
  const q = quote.data;
  const money = (amount: string) => formatMoney(amount, q.currency);
  const refresh = () => queryClient.invalidateQueries({ queryKey: getQuotesGetQueryKey(quoteId) });

  async function send() {
    setBusy(true);
    setError(null);
    try {
      const target = email ?? q.client.email ?? "";
      const result = await quotesSend(quoteId, { email: target || undefined, message });
      setSent(result);
      toast.success(result.emailed_to ? `Sent to ${result.emailed_to}` : "Link ready to share");
      await refresh();
    } catch (e) {
      setError(e instanceof ApiError ? problemMessage(e.problem) : "The quote was not sent. Try again.");
    } finally {
      setBusy(false);
    }
  }

  async function openPdf() {
    const { url } = await quotesPdf(quoteId);
    window.open(url, "_blank", "noopener");
  }

  return (
    <div className="grid gap-6">
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <h1 className="text-3xl">{q.title}</h1>
          <p className="mt-1 text-muted-foreground">
            {q.number ?? "Not numbered yet"} · for <Link className="font-bold text-primary hover:underline" href={`/clients/${q.client.id}`}>{q.client.display_name}</Link> · valid until {formatDate(q.valid_until)}
          </p>
          <div className="mt-2"><QuoteStatus status={q.status} /></div>
        </div>
        <div className="flex flex-wrap gap-2">
          {q.document_id && <Button variant="outline" onClick={openPdf}><FileDown aria-hidden="true" /> PDF</Button>}
          {canWrite && ["accepted", "sent", "expired"].includes(q.status) && (
            <Button asChild variant={q.status === "accepted" ? "default" : "outline"}><Link href={`/policies/new?quote=${q.id}`}><ShieldCheck aria-hidden="true" /> {q.status === "accepted" ? "Create policy" : "Client accepted by phone"}</Link></Button>
          )}
          {canWrite && ["draft", "sent"].includes(q.status) && (
            <Button onClick={() => setSending(true)}><Send aria-hidden="true" /> {q.status === "draft" ? "Send to client" : "Send again"}</Button>
          )}
          {canWrite && ["draft", "sent"].includes(q.status) && (
            <Button variant="ghost" className="text-destructive" onClick={async () => { await quotesWithdraw(quoteId); await refresh(); toast.success("Quote withdrawn"); }}>Withdraw</Button>
          )}
        </div>
      </div>

      {q.response && Object.keys(q.response).length > 0 && (
        <p className={cn("rounded-md border px-3 py-2", q.status === "accepted" ? "border-primary bg-accent" : "border-destructive/40")}>
          {q.status === "accepted"
            ? <>Accepted option {q.accepted_position} by <strong>{String(q.response.name)}</strong> on {formatDate(q.responded_at ?? "")}{q.response.phone ? ` (${String(q.response.phone)})` : ""}. Next: confirm cover with the insurer and create the policy.</>
            : <>Declined on {formatDate(q.responded_at ?? "")}{q.response.reason ? `: “${String(q.response.reason)}”` : ""}.</>}
        </p>
      )}

      {q.details.length > 0 && (
        <dl className="grid gap-x-8 gap-y-1 sm:grid-cols-2">
          {q.details.map((d) => <div key={d.label}><dt className="text-sm text-muted-foreground">{d.label}</dt><dd className="font-bold">{d.value}</dd></div>)}
        </dl>
      )}

      <ol className="grid gap-3" aria-label="Options">
        {q.option_list.map((o) => {
          const breakdown = o.breakdown as unknown as Breakdown;
          return (
            <li key={o.position} className={cn("rounded-lg border bg-card", q.accepted_position === o.position && "border-primary ring-2 ring-primary/15")}>
              <div className="flex flex-wrap items-baseline gap-x-4 gap-y-1 border-b px-4 py-3">
                <span className="min-w-0 flex-1">
                  <span className="block font-bold">{o.position}. {o.insurer_name}{o.recommended && <span className="ml-2 rounded-full bg-maize px-2 py-0.5 text-xs text-ink">Recommended</span>}</span>
                  <span className="text-sm text-muted-foreground">{o.product_name}</span>
                </span>
                <span className="tabular font-heading text-2xl">{o.needs_input ? "Needs details" : money(o.client_total)}</span>
              </div>
              <table className="w-full text-sm">
                <caption className="sr-only">Breakdown of option {o.position}</caption>
                <tbody>
                  {breakdown.lines.filter((l) => l.charged_to === "client").map((l) => (
                    <tr key={l.code} className="border-b last:border-0"><th scope="row" className="px-4 py-1.5 text-left font-normal">{l.label}</th><td className="tabular px-4 py-1.5 text-right">{money(l.amount)}</td></tr>
                  ))}
                </tbody>
              </table>
              {o.commission && (
                <p className="px-4 py-2 text-sm text-muted-foreground">
                  Your commission {money(String(o.commission.gross))} ({fractionToPercent(String(o.commission.rate))}%), net of withholding tax {money(String(o.commission.net))}. Not shown to the client.
                </p>
              )}
            </li>
          );
        })}
      </ol>
      {q.notes && <p className="max-w-prose whitespace-pre-line text-muted-foreground">{q.notes}</p>}

      <Dialog open={sending} onOpenChange={(open) => { setSending(open); if (!open) setSent(null); }}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>{sent ? "Quote sent" : "Send to client"}</DialogTitle>
            <DialogDescription>{sent ? "Share the link on WhatsApp too, if you like." : "The client gets a link to view the quote, download the PDF and accept an option."}</DialogDescription>
          </DialogHeader>
          {sent ? (
            <div className="grid gap-3">
              <Input readOnly value={sent.url} aria-label="Quote link" onFocus={(e) => e.target.select()} />
              <div className="flex flex-wrap gap-2">
                <Button variant="outline" onClick={async () => { await navigator.clipboard.writeText(sent.url); toast.success("Link copied"); }}><Copy /> Copy link</Button>
                {sent.whatsapp_url && <Button asChild><a href={sent.whatsapp_url} target="_blank" rel="noopener noreferrer"><MessageCircle /> Share on WhatsApp</a></Button>}
              </div>
            </div>
          ) : (
            <div className="grid gap-4">
              <FormError message={error} />
              <Field label="Client email" optional hint="Leave empty to only create a link to share yourself.">
                {(p) => <Input {...p} type="email" value={email ?? q.client.email ?? ""} onChange={(e) => setEmail(e.target.value)} />}
              </Field>
              <Field label="Message" optional>{(p) => <Textarea {...p} rows={3} value={message} onChange={(e) => setMessage(e.target.value)} />}</Field>
            </div>
          )}
          {!sent && <DialogFooter><Button onClick={send} disabled={busy}>{busy ? "Sending…" : "Send quote"}</Button></DialogFooter>}
        </DialogContent>
      </Dialog>
    </div>
  );
}
