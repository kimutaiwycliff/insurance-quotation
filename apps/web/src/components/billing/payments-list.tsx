"use client";

import { FileDown } from "lucide-react";
import Link from "next/link";
import { useState } from "react";
import { toast } from "sonner";

import { METHOD_LABELS } from "@/components/billing/status";
import { useCan } from "@/components/shell/me-context";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Skeleton } from "@/components/ui/skeleton";
import { Textarea } from "@/components/ui/textarea";
import { paymentsReceipt, paymentsVoid, usePaymentsList } from "@/lib/api/generated/billing/billing";
import type { ReceivedPayment } from "@/lib/api/generated/model";
import { formatDate, formatMoney } from "@/lib/format";
import { ApiError, problemMessage } from "@/lib/problem";
import { cn } from "@/lib/utils";

export function PaymentsList({ clientId }: { clientId?: string }) {
  const payments = usePaymentsList(clientId ? { client_id: clientId } : undefined);
  const canPay = useCan("payment:write");
  const [voiding, setVoiding] = useState<ReceivedPayment | null>(null);
  const [reason, setReason] = useState("");

  async function receipt(id: string) {
    const { url } = await paymentsReceipt(id);
    window.open(url, "_blank", "noopener");
  }

  if (!payments.data) return <Skeleton className="h-40 w-full" />;
  if (payments.data.length === 0) return <p className="rounded-lg border border-dashed bg-card px-4 py-10 text-center text-muted-foreground">No payments recorded yet.</p>;
  return (
    <>
      <ul className="divide-y rounded-lg border bg-card" aria-label="Payments">
        {payments.data.map((p) => (
          <li key={p.id} className={cn("grid gap-1 px-4 py-3 sm:grid-cols-[minmax(0,2fr)_minmax(0,1fr)_auto] sm:items-center sm:gap-4", p.voided_at && "text-muted-foreground")}>
            <span className="min-w-0">
              <span className="block font-bold">{p.number}{clientId ? "" : <> · <Link className="hover:underline" href={`/clients/${p.client.id}`}>{p.client.display_name}</Link></>}</span>
              <span className="text-sm text-muted-foreground">
                {formatDate(p.received_on)} · {METHOD_LABELS[p.method] ?? p.method}{p.reference ? ` ${p.reference}` : ""}
                {p.allocations.length > 0 && ` · for ${p.allocations.map((a) => a.invoice_number).join(", ")}`}
                {p.voided_at && ` · voided: ${p.void_reason}`}
              </span>
            </span>
            <span className={cn("tabular", p.voided_at && "line-through")}>
              {formatMoney(p.amount, p.currency)}
              {Number(p.unallocated) > 0 && <span className="block text-sm text-muted-foreground">{formatMoney(p.unallocated, p.currency)} credit</span>}
            </span>
            <span className="flex gap-1">
              <Button size="sm" variant="outline" onClick={() => receipt(p.id)}><FileDown aria-hidden="true" /> Receipt</Button>
              {canPay && !p.voided_at && <Button size="sm" variant="ghost" onClick={() => setVoiding(p)}>Void</Button>}
            </span>
          </li>
        ))}
      </ul>
      <Dialog open={voiding !== null} onOpenChange={(o) => !o && setVoiding(null)}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Void payment {voiding?.number}</DialogTitle>
            <DialogDescription>For a bounced cheque or a payment entered by mistake. The invoices it paid become unpaid again.</DialogDescription>
          </DialogHeader>
          <Textarea aria-label="Reason" rows={2} value={reason} onChange={(e) => setReason(e.target.value)} />
          <DialogFooter>
            <Button variant="destructive" disabled={reason.trim().length < 2} onClick={async () => {
              try {
                await paymentsVoid(voiding!.id, { reason: reason.trim() });
                toast.success("Payment voided");
                setVoiding(null);
                setReason("");
                await payments.refetch();
              } catch (e) {
                toast.error(e instanceof ApiError ? problemMessage(e.problem) : "Not voided. Try again.");
              }
            }}>Void payment</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </>
  );
}
