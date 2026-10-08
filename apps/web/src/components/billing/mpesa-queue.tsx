"use client";

import { useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { toast } from "sonner";

import { Field, FormError } from "@/components/forms/field";
import { useCan } from "@/components/shell/me-context";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { NativeSelect } from "@/components/ui/native-select";
import { Textarea } from "@/components/ui/textarea";
import { useInvoicesList } from "@/lib/api/generated/billing/billing";
import { useClientsList } from "@/lib/api/generated/clients/clients";
import type { TransactionOut } from "@/lib/api/generated/model";
import { getMpesaTransactionsListQueryKey, mpesaTransactionsIgnore, mpesaTransactionsMatch, useMpesaTransactionsList } from "@/lib/api/generated/mpesa/mpesa";
import { formatDate, formatMoney } from "@/lib/format";
import { useDebounced } from "@/lib/use-debounced";
import { ApiError, problemMessage } from "@/lib/problem";

function MatchDialog({ txn, onClose }: { txn: TransactionOut; onClose: (changed: boolean) => void }) {
  const [q, setQ] = useState(txn.payer ?? "");
  const search = useDebounced(q, 300);
  const clients = useClientsList({ q: search.trim().length >= 2 ? search.trim() : undefined, limit: 10 });
  const [clientId, setClientId] = useState("");
  const invoices = useInvoicesList({ client_id: clientId, status: "unpaid" }, { query: { enabled: Boolean(clientId) } });
  const [invoiceId, setInvoiceId] = useState("");
  const [reason, setReason] = useState("");
  const [mode, setMode] = useState<"match" | "ignore">("match");
  const [error, setError] = useState<string | null>(null);

  async function save() {
    setError(null);
    try {
      if (mode === "match") await mpesaTransactionsMatch(txn.id, { client_id: clientId, invoice_id: invoiceId || undefined });
      else await mpesaTransactionsIgnore(txn.id, { reason: reason.trim() });
      toast.success(mode === "match" ? "Payment matched" : "Payment set aside");
      onClose(true);
    } catch (e) {
      setError(e instanceof ApiError ? problemMessage(e.problem) : "Not saved. Try again.");
    }
  }

  return (
    <Dialog open onOpenChange={(o) => !o && onClose(false)}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>{formatMoney(txn.amount, "KES")} from {txn.payer ?? "an M-Pesa customer"}</DialogTitle>
          <DialogDescription>Receipt {txn.receipt}. Account typed: {txn.bill_reference || "nothing"}.</DialogDescription>
        </DialogHeader>
        <div role="tablist" aria-label="What to do" className="flex gap-1">
          {(["match", "ignore"] as const).map((m) => (
            <button key={m} role="tab" type="button" aria-selected={mode === m} onClick={() => setMode(m)} className={`rounded-full border px-3 py-1.5 text-sm ${mode === m ? "border-primary bg-primary text-primary-foreground" : ""}`}>
              {m === "match" ? "Assign to a client" : "Not a client payment"}
            </button>
          ))}
        </div>
        <FormError message={error} />
        {mode === "match" ? (
          <div className="grid gap-4">
            <Field label="Find the client">{(p) => <Input {...p} value={q} onChange={(e) => setQ(e.target.value)} placeholder="Name or phone" />}</Field>
            <Field label="Client">
              {(p) => (
                <NativeSelect {...p} value={clientId} onChange={(e) => { setClientId(e.target.value); setInvoiceId(""); }}>
                  <option value="">Choose…</option>
                  {(clients.data?.items ?? []).map((c) => <option key={c.id} value={c.id}>{c.display_name}</option>)}
                </NativeSelect>
              )}
            </Field>
            {clientId && (
              <Field label="Invoice" optional hint="Leave empty to keep it as the client's credit.">
                {(p) => (
                  <NativeSelect {...p} value={invoiceId} onChange={(e) => setInvoiceId(e.target.value)}>
                    <option value="">Keep as credit</option>
                    {(invoices.data ?? []).map((i) => <option key={i.id} value={i.id}>{i.number} · {formatMoney(i.balance, i.currency)} due</option>)}
                  </NativeSelect>
                )}
              </Field>
            )}
          </div>
        ) : (
          <Field label="Why">{(p) => <Textarea {...p} rows={2} value={reason} onChange={(e) => setReason(e.target.value)} placeholder="e.g. Owner's own transfer" />}</Field>
        )}
        <DialogFooter>
          <Button disabled={mode === "match" ? !clientId : reason.trim().length < 2} onClick={save}>{mode === "match" ? "Assign payment" : "Set aside"}</Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

/** M-Pesa payments that could not be matched to an invoice (e.g. a mistyped account number). */
export function MpesaQueue() {
  const queryClient = useQueryClient();
  const canPay = useCan("payment:write");
  const queue = useMpesaTransactionsList({ status: "unmatched" }, { query: { enabled: canPay } });
  const [open, setOpen] = useState<TransactionOut | null>(null);
  if (!canPay || !queue.data || queue.data.length === 0) return null;
  return (
    <section aria-labelledby="queue-heading" className="grid gap-2 rounded-lg border border-maize p-4">
      <h2 id="queue-heading" className="text-xl">M-Pesa payments to match ({queue.data.length})</h2>
      <p className="text-sm text-muted-foreground">These came into your Paybill without a reference we recognise.</p>
      <ul className="divide-y rounded-md border bg-card">
        {queue.data.map((t) => (
          <li key={t.id} className="flex flex-wrap items-center gap-3 px-3 py-2">
            <span className="min-w-0 flex-1">
              <span className="block font-bold">{formatMoney(t.amount, "KES")} · {t.payer ?? "Unknown payer"}</span>
              <span className="text-sm text-muted-foreground">{t.receipt} · account &ldquo;{t.bill_reference || "blank"}&rdquo;{t.paid_at ? ` · ${formatDate(t.paid_at)}` : ""}</span>
            </span>
            <Button size="sm" onClick={() => setOpen(t)}>Match</Button>
          </li>
        ))}
      </ul>
      {open && <MatchDialog txn={open} onClose={async (changed) => { setOpen(null); if (changed) await queryClient.invalidateQueries({ queryKey: getMpesaTransactionsListQueryKey({ status: "unmatched" }) }); }} />}
    </section>
  );
}
