"use client";

import { useQueryClient } from "@tanstack/react-query";
import { Copy, FileDown, MessageCircle, Pencil, Send } from "lucide-react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState } from "react";
import { toast } from "sonner";

import { InvoiceEditor } from "@/components/billing/invoice-editor";
import { BillingStatus, METHOD_LABELS } from "@/components/billing/status";
import { Field, FormError } from "@/components/forms/field";
import { todayIso } from "@/components/policies/new-policy";
import { useCan } from "@/components/shell/me-context";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { NativeSelect } from "@/components/ui/native-select";
import { Skeleton } from "@/components/ui/skeleton";
import { Textarea } from "@/components/ui/textarea";
import {
  billingDocumentsIssue,
  billingDocumentsPdf,
  billingDocumentsSend,
  billingDocumentsVoid,
  creditNotesCreate,
  getBillingDocumentsGetQueryKey,
  invoicesApplyCredit,
  paymentsCreate,
  useBillingDocumentsGet,
  useClientsAccount,
} from "@/lib/api/generated/billing/billing";
import type { BillingDocumentOut, PaymentCreateMethod, DocumentSent } from "@/lib/api/generated/model";
import { formatDate, formatMoney, fractionToPercent } from "@/lib/format";
import { ApiError, problemMessage } from "@/lib/problem";

function useRun(onDone: () => Promise<unknown>) {
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

function RecordPayment({ doc, open, onOpenChange, refresh }: { doc: BillingDocumentOut; open: boolean; onOpenChange: (o: boolean) => void; refresh: () => Promise<unknown> }) {
  const [amount, setAmount] = useState(doc.balance);
  const [receivedOn, setReceivedOn] = useState(todayIso());
  const [method, setMethod] = useState<PaymentCreateMethod>("mpesa");
  const [reference, setReference] = useState("");
  const { busy, error, run } = useRun(refresh);
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Record a payment</DialogTitle>
          <DialogDescription>Money {doc.client.display_name} paid into your account. Anything above {formatMoney(doc.balance, doc.currency)} is kept as their credit.</DialogDescription>
        </DialogHeader>
        <div className="grid gap-4">
          <FormError message={error} />
          <div className="grid gap-4 sm:grid-cols-2">
            <Field label={`Amount (${doc.currency})`}>{(p) => <Input {...p} inputMode="decimal" value={amount} onChange={(e) => setAmount(e.target.value.replace(/[, ]/g, ""))} />}</Field>
            <Field label="Received on">{(p) => <Input {...p} type="date" value={receivedOn} onChange={(e) => setReceivedOn(e.target.value)} />}</Field>
            <Field label="Method">
              {(p) => <NativeSelect {...p} value={method} onChange={(e) => setMethod(e.target.value as PaymentCreateMethod)}>{Object.entries(METHOD_LABELS).map(([v, l]) => <option key={v} value={v}>{l}</option>)}</NativeSelect>}
            </Field>
            <Field label="Reference" optional hint="e.g. the M-Pesa code">{(p) => <Input {...p} value={reference} onChange={(e) => setReference(e.target.value)} />}</Field>
          </div>
        </div>
        <DialogFooter>
          <Button disabled={busy || !amount} onClick={async () => {
            const ok = await run(async () => {
              const applied = Number(amount) >= Number(doc.balance) ? doc.balance : amount;
              await paymentsCreate({ client_id: doc.client.id, amount, received_on: receivedOn, method, reference: reference || undefined, allocations: [{ invoice_id: doc.id, amount: applied }] });
            }, "Payment recorded");
            if (ok) onOpenChange(false);
          }}>Record payment</Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

function SendDialog({ doc, open, onOpenChange, refresh }: { doc: BillingDocumentOut; open: boolean; onOpenChange: (o: boolean) => void; refresh: () => Promise<unknown> }) {
  const [email, setEmail] = useState<string | null>(null);
  const [message, setMessage] = useState("");
  const [sent, setSent] = useState<DocumentSent | null>(null);
  const { busy, error, run } = useRun(refresh);
  const label = doc.kind === "invoice" ? "invoice" : "credit note";
  return (
    <Dialog open={open} onOpenChange={(o) => { onOpenChange(o); if (!o) setSent(null); }}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>{sent ? `${label[0]!.toUpperCase()}${label.slice(1)} sent` : `Send ${label}`}</DialogTitle>
          <DialogDescription>{sent ? "Share the link on WhatsApp too, if you like." : `The client gets a link to view and download the ${label}.`}</DialogDescription>
        </DialogHeader>
        {sent ? (
          <div className="grid gap-3">
            <Input readOnly value={sent.url} aria-label="Link" onFocus={(e) => e.target.select()} />
            <div className="flex flex-wrap gap-2">
              <Button variant="outline" onClick={async () => { await navigator.clipboard.writeText(sent.url); toast.success("Link copied"); }}><Copy /> Copy link</Button>
              {sent.whatsapp_url && <Button asChild><a href={sent.whatsapp_url} target="_blank" rel="noopener noreferrer"><MessageCircle /> Share on WhatsApp</a></Button>}
            </div>
          </div>
        ) : (
          <div className="grid gap-4">
            <FormError message={error} />
            <Field label="Client email" optional hint="Leave empty to only create a link to share yourself.">
              {(p) => <Input {...p} type="email" value={email ?? doc.client.email ?? ""} onChange={(e) => setEmail(e.target.value)} />}
            </Field>
            <Field label="Message" optional>{(p) => <Textarea {...p} rows={3} value={message} onChange={(e) => setMessage(e.target.value)} />}</Field>
          </div>
        )}
        {!sent && (
          <DialogFooter>
            <Button disabled={busy} onClick={() => run(async () => {
              const target = email ?? doc.client.email ?? "";
              setSent(await billingDocumentsSend(doc.id, { email: target || undefined, message }));
            })}>Send</Button>
          </DialogFooter>
        )}
      </DialogContent>
    </Dialog>
  );
}

function ReasonDialog({ title, description, action, open, onOpenChange, onConfirm, error, busy }: {
  title: string; description: string; action: string; open: boolean; onOpenChange: (o: boolean) => void;
  onConfirm: (reason: string) => void; error: string | null; busy: boolean;
}) {
  const [reason, setReason] = useState("");
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>{title}</DialogTitle>
          <DialogDescription>{description}</DialogDescription>
        </DialogHeader>
        <FormError message={error} />
        <Textarea aria-label="Reason" rows={2} value={reason} onChange={(e) => setReason(e.target.value)} />
        <DialogFooter><Button disabled={busy || reason.trim().length < 2} onClick={() => onConfirm(reason.trim())}>{action}</Button></DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

export function InvoiceDetail({ documentId }: { documentId: string }) {
  const router = useRouter();
  const queryClient = useQueryClient();
  const doc = useBillingDocumentsGet(documentId);
  const account = useClientsAccount(doc.data?.client.id ?? "", { query: { enabled: Boolean(doc.data && doc.data.kind === "invoice") } });
  const canWrite = useCan("invoice:write");
  const canIssue = useCan("invoice:issue");
  const canPay = useCan("payment:write");
  const [editing, setEditing] = useState(false);
  const [dialog, setDialog] = useState<"pay" | "send" | "void" | "credit" | null>(null);
  const refresh = () => Promise.all([
    queryClient.invalidateQueries({ queryKey: getBillingDocumentsGetQueryKey(documentId) }),
    account.refetch(),
  ]);
  const { busy, error, setError, run } = useRun(refresh);

  if (!doc.data) return <Skeleton className="h-96 w-full" />;
  const d = doc.data;
  if (editing) return <InvoiceEditor clientId={d.client.id} draft={d} />;
  const money = (a: string) => formatMoney(a, d.currency);
  const isInvoice = d.kind === "invoice";
  const issued = d.status !== "draft" && d.status !== "void";
  const credit = account.data ? Number(account.data.credit) : 0;

  async function openPdf() {
    const { url } = await billingDocumentsPdf(documentId);
    window.open(url, "_blank", "noopener");
  }

  return (
    <div className="grid gap-6">
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <h1 className="text-3xl">{isInvoice ? "Invoice" : "Credit note"} {d.number ?? "(draft)"}</h1>
          <p className="mt-1 text-muted-foreground">
            <Link className="font-bold text-primary hover:underline" href={`/clients/${d.client.id}`}>{d.client.display_name}</Link>
            {d.issue_date ? ` · issued ${formatDate(d.issue_date)}` : ""}{isInvoice && d.due_date && issued ? ` · due ${formatDate(d.due_date)}` : ""}
          </p>
          <div className="mt-2"><BillingStatus status={d.status} /></div>
        </div>
        <div className="flex flex-wrap gap-2">
          {d.status === "draft" && canWrite && <Button variant="outline" onClick={() => setEditing(true)}><Pencil aria-hidden="true" /> Edit</Button>}
          {d.status === "draft" && canIssue && (
            <Button onClick={() => run(() => billingDocumentsIssue(documentId, {}), `${isInvoice ? "Invoice" : "Credit note"} issued`)} disabled={busy}>Issue</Button>
          )}
          <Button variant="outline" onClick={openPdf}><FileDown aria-hidden="true" /> PDF</Button>
          {issued && canIssue && <Button variant={isInvoice && Number(d.balance) > 0 ? "outline" : "default"} onClick={() => setDialog("send")}><Send aria-hidden="true" /> Send</Button>}
          {isInvoice && issued && canPay && Number(d.balance) > 0 && <Button onClick={() => setDialog("pay")}>Record payment</Button>}
        </div>
      </div>
      <FormError message={error} />

      {isInvoice && issued && canPay && Number(d.balance) > 0 && credit > 0 && (
        <p className="flex flex-wrap items-center gap-3 rounded-md border border-primary bg-accent px-3 py-2">
          {d.client.display_name} has {formatMoney(account.data!.credit, d.currency)} of credit on account.
          <Button size="sm" disabled={busy} onClick={() => run(() => invoicesApplyCredit(documentId), "Credit applied")}>Use it on this invoice</Button>
        </p>
      )}
      {d.voided_at && <p className="rounded-md border border-destructive/40 px-3 py-2">Voided on {formatDate(d.voided_at)}: {d.void_reason}</p>}

      <div className="overflow-x-auto rounded-lg border bg-card" tabIndex={0} role="region" aria-label="Lines">
        <table className="w-full min-w-[36rem] text-sm">
          <thead><tr className="border-b text-left text-muted-foreground"><th className="px-3 py-2 font-normal">Description</th><th className="px-3 py-2 text-right font-normal">Qty</th><th className="px-3 py-2 text-right font-normal">Price</th><th className="px-3 py-2 font-normal">Tax</th><th className="px-3 py-2 text-right font-normal">Amount</th></tr></thead>
          <tbody>
            {d.lines.map((l) => (
              <tr key={l.position} className="border-b last:border-0">
                <td className="px-3 py-2">{l.description}{Number(l.discount_rate) > 0 && <span className="block text-xs text-muted-foreground">{fractionToPercent(l.discount_rate)}% discount</span>}</td>
                <td className="tabular px-3 py-2 text-right">{l.quantity}</td>
                <td className="tabular px-3 py-2 text-right">{money(l.unit_price)}</td>
                <td className="px-3 py-2">{fractionToPercent(l.tax_rate)}%</td>
                <td className="tabular px-3 py-2 text-right">{money(l.net)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <dl className="ml-auto grid w-full max-w-xs gap-1 text-sm">
        <div className="flex justify-between"><dt>Subtotal</dt><dd className="tabular">{money(d.subtotal)}</dd></div>
        {d.taxes.filter((t) => Number(t.tax) > 0).map((t) => <div key={t.code} className="flex justify-between"><dt>{t.name}</dt><dd className="tabular">{money(t.tax)}</dd></div>)}
        <div className="flex justify-between border-t pt-1 font-bold"><dt>Total</dt><dd className="tabular">{money(d.total)}</dd></div>
        {isInvoice && issued && Number(d.paid) > 0 && <div className="flex justify-between"><dt>Paid</dt><dd className="tabular">{money(d.paid)}</dd></div>}
        {isInvoice && issued && <div className="flex justify-between font-bold"><dt>Balance</dt><dd className="tabular">{money(d.balance)}</dd></div>}
      </dl>
      {isInvoice && d.payment_reference && <p className="text-sm text-muted-foreground">Payment reference for M-Pesa: <strong className="tabular text-foreground">{d.payment_reference}</strong></p>}
      {d.notes && <p className="max-w-prose whitespace-pre-line text-muted-foreground">{d.notes}</p>}

      {d.allocations.length > 0 && (
        <section aria-labelledby="applied-heading" className="grid gap-2">
          <h2 id="applied-heading" className="text-xl">{isInvoice ? "Payments and credits" : "Applied to"}</h2>
          <ul className="divide-y rounded-lg border bg-card text-sm">
            {d.allocations.map((a) => (
              <li key={a.id} className="flex flex-wrap justify-between gap-2 px-4 py-2">
                <span>{isInvoice ? (a.source === "payment" ? `Payment ${a.source_number}` : `Credit note ${a.source_number}`) : `Invoice ${a.invoice_number}`} · {formatDate(a.created_at)}</span>
                <span className="tabular">{money(a.amount)}</span>
              </li>
            ))}
          </ul>
        </section>
      )}
      {d.credits_document_id && <p className="text-sm"><Link className="text-primary hover:underline" href={`/invoices/${d.credits_document_id}`}>The invoice this credits</Link></p>}

      {canIssue && issued && (
        <div className="flex flex-wrap gap-2">
          {isInvoice && <Button variant="outline" onClick={() => setDialog("credit")}>Issue a credit note</Button>}
          <Button variant="ghost" className="text-destructive" onClick={() => { setError(null); setDialog("void"); }}>Void</Button>
        </div>
      )}
      {canWrite && d.status === "draft" && (
        <div><Button variant="ghost" className="text-destructive" onClick={() => setDialog("void")}>Delete draft</Button></div>
      )}

      {isInvoice && <RecordPayment doc={d} open={dialog === "pay"} onOpenChange={(o) => setDialog(o ? "pay" : null)} refresh={refresh} />}
      <SendDialog doc={d} open={dialog === "send"} onOpenChange={(o) => setDialog(o ? "send" : null)} refresh={refresh} />
      <ReasonDialog
        title={d.status === "draft" ? "Delete this draft" : `Void ${d.number}`}
        description={d.status === "draft" ? "The draft is kept in the history as void." : "Only possible while nothing has been paid or credited against it. The number stays used."}
        action={d.status === "draft" ? "Delete draft" : "Void"}
        open={dialog === "void"}
        onOpenChange={(o) => setDialog(o ? "void" : null)}
        busy={busy}
        error={error}
        onConfirm={async (reason) => { if (await run(() => billingDocumentsVoid(documentId, { reason }), "Done")) setDialog(null); }}
      />
      <ReasonDialog
        title={`Credit note for ${d.number}`}
        description="Credits the whole invoice. Adjust the lines on the draft before you issue it."
        action="Create credit note"
        open={dialog === "credit"}
        onOpenChange={(o) => setDialog(o ? "credit" : null)}
        busy={busy}
        error={error}
        onConfirm={async (reason) => {
          await run(async () => {
            const cn = await creditNotesCreate({ invoice_id: documentId, reason });
            router.push(`/invoices/${cn.id}`);
          });
        }}
      />
    </div>
  );
}
