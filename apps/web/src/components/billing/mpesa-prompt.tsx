"use client";

import { Smartphone } from "lucide-react";
import { useEffect, useState } from "react";
import { toast } from "sonner";

import { Field, FormError } from "@/components/forms/field";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import type { PromptOut } from "@/lib/api/generated/model";
import { invoicesMpesaPrompt, mpesaPromptGet, useMpesaConnectionGet } from "@/lib/api/generated/mpesa/mpesa";
import { formatMoney, formatPhone } from "@/lib/format";
import { ApiError, problemMessage } from "@/lib/problem";

const DONE = new Set(["paid", "cancelled", "failed", "expired"]);
const TEXT: Record<string, string> = {
  pending: "Waiting for the client to enter their M-Pesa PIN…",
  paid: "Paid. The payment is recorded on the invoice.",
  cancelled: "The client cancelled the prompt.",
  expired: "The prompt timed out. Try again.",
};

/** Sends an M-Pesa payment prompt to the client's phone and follows it until it is paid or ends. */
export function MpesaPromptButton({ invoiceId, clientPhone, balance, onPaid }: { invoiceId: string; clientPhone: string | null; balance: string; onPaid: () => Promise<unknown> }) {
  const [open, setOpen] = useState(false);
  const [phone, setPhone] = useState(formatPhone(clientPhone) ?? "");
  const [prompt, setPrompt] = useState<PromptOut | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [misses, setMisses] = useState(0);
  const connection = useMpesaConnectionGet();

  useEffect(() => {
    if (!prompt || DONE.has(prompt.status)) return;
    const timer = window.setTimeout(async () => {
      try {
        const next = await mpesaPromptGet(prompt.id);
        setPrompt(next);
        if (next.status === "paid") {
          toast.success(`M-Pesa payment received${next.receipt ? `: ${next.receipt}` : ""}`);
          await onPaid();
        }
        setMisses(0);
      } catch {
        setMisses((n) => n + 1); // keep polling; say so if the status cannot be fetched for a while
      }
    }, 3000);
    return () => window.clearTimeout(timer);
  }, [prompt, onPaid]);

  async function send() {
    setBusy(true);
    setError(null);
    try {
      setPrompt(await invoicesMpesaPrompt(invoiceId, { phone: phone || undefined }));
    } catch (e) {
      setError(e instanceof ApiError ? problemMessage(e.problem) : "The prompt was not sent. Try again.");
    } finally {
      setBusy(false);
    }
  }

  if (connection.data?.status !== "active") return null;
  return (
    <>
      {Number(balance) > 0 && (
        <Button variant="outline" onClick={() => { setPrompt(null); setError(null); setOpen(true); }}>
          <Smartphone aria-hidden="true" /> Ask for M-Pesa payment
        </Button>
      )}
      <Dialog open={open} onOpenChange={setOpen}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>M-Pesa payment prompt</DialogTitle>
            <DialogDescription>
              The client gets a prompt on their phone for {formatMoney(String(Math.ceil(Number(balance))), "KES")} (M-Pesa takes whole shillings) and enters their PIN. The money goes to your Paybill or Till.
            </DialogDescription>
          </DialogHeader>
          <FormError message={error} />
          {prompt ? (
            <p role="status" aria-live="polite" className={prompt.status === "paid" ? "font-bold text-primary" : DONE.has(prompt.status) ? "font-bold text-destructive" : ""}>
              {TEXT[prompt.status] ?? prompt.result_desc ?? "The payment did not go through."}
              {prompt.receipt && ` Receipt ${prompt.receipt}.`}
              {misses >= 3 && !DONE.has(prompt.status) && " (We cannot reach the server right now; still trying.)"}
            </p>
          ) : (
            <Field label="Client's M-Pesa number">{(p) => <Input {...p} type="tel" inputMode="tel" value={phone} onChange={(e) => setPhone(e.target.value)} placeholder="0712 345 678" />}</Field>
          )}
          <DialogFooter>
            {!prompt || DONE.has(prompt.status) ? (
              prompt?.status === "paid" ? <Button onClick={() => setOpen(false)}>Done</Button> : <Button disabled={busy || !phone} onClick={send}>{prompt ? "Send again" : "Send prompt"}</Button>
            ) : (
              <Button variant="ghost" onClick={() => setOpen(false)}>Close (it keeps going)</Button>
            )}
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </>
  );
}
