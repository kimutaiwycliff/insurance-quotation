"use client";

import { useQueryClient } from "@tanstack/react-query";
import { CheckCircle2, Copy, CreditCard } from "lucide-react";
import { useState } from "react";
import { toast } from "sonner";

import { Field, FormError } from "@/components/forms/field";
import { useCan } from "@/components/shell/me-context";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { NativeSelect } from "@/components/ui/native-select";
import { Skeleton } from "@/components/ui/skeleton";
import type { ConnectionInEnvironment, ConnectionInShortcodeType } from "@/lib/api/generated/model";
import {
  getMpesaConnectionGetQueryKey,
  mpesaConnectionDisable,
  mpesaConnectionRegisterC2b,
  mpesaConnectionSave,
  useMpesaConnectionGet,
} from "@/lib/api/generated/mpesa/mpesa";
import { formatDate } from "@/lib/format";
import { ApiError, problemMessage } from "@/lib/problem";

function CopyRow({ label, value }: { label: string; value: string }) {
  return (
    <div className="grid gap-1">
      <span className="text-sm text-muted-foreground">{label}</span>
      <div className="flex gap-2">
        <Input readOnly value={value} aria-label={label} onFocus={(e) => e.target.select()} className="font-mono text-xs" />
        <Button type="button" variant="outline" size="icon" aria-label={`Copy ${label}`} onClick={async () => { await navigator.clipboard.writeText(value); toast.success("Copied"); }}><Copy /></Button>
      </div>
    </div>
  );
}

export function MpesaSettings() {
  const queryClient = useQueryClient();
  const connection = useMpesaConnectionGet();
  const canEdit = useCan("org:update");
  const [editing, setEditing] = useState(false);
  const [environment, setEnvironment] = useState<ConnectionInEnvironment>("production");
  const [type, setType] = useState<ConnectionInShortcodeType>("paybill");
  const [shortcode, setShortcode] = useState("");
  const [till, setTill] = useState("");
  const [key, setKey] = useState("");
  const [secret, setSecret] = useState("");
  const [passkey, setPasskey] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const refresh = () => queryClient.invalidateQueries({ queryKey: getMpesaConnectionGetQueryKey() });

  async function run(fn: () => Promise<unknown>, success: string) {
    setBusy(true);
    setError(null);
    try {
      await fn();
      await refresh();
      toast.success(success);
      return true;
    } catch (e) {
      setError(e instanceof ApiError ? problemMessage(e.problem) : "That did not work. Try again.");
      return false;
    } finally {
      setBusy(false);
    }
  }

  if (connection.isLoading) return <Skeleton className="h-64 w-full" />;
  const c = connection.data ?? null;
  const showForm = canEdit && (editing || !c);

  return (
    <div className="grid max-w-2xl gap-8">
      <section aria-labelledby="mpesa-heading" className="grid gap-4">
        <div className="flex flex-wrap items-center gap-3">
          <h2 id="mpesa-heading" className="text-xl">M-Pesa</h2>
          {c && <Badge variant={c.status === "active" ? "default" : "secondary"}>{c.status === "active" ? "Connected" : "Turned off"}</Badge>}
          {c?.environment === "sandbox" && <Badge variant="outline">Sandbox</Badge>}
          {c?.environment === "simulator" && <Badge variant="outline">Simulator</Badge>}
        </div>
        <p className="text-muted-foreground">
          Clients pay straight into your own Paybill or Till: from a payment prompt on their phone, or by paying your Paybill with the invoice&apos;s payment reference as the account number. The money never passes through us.
        </p>
        <FormError message={error} />
        {c && !showForm && (
          <div className="grid gap-4 rounded-lg border bg-card p-4">
            <dl className="grid grid-cols-2 gap-3 text-sm">
              <div><dt className="text-muted-foreground">{c.shortcode_type === "till" ? "Till" : "Paybill"}</dt><dd className="font-bold">{c.party_b}</dd></div>
              <div><dt className="text-muted-foreground">Consumer key</dt><dd className="font-bold">{c.consumer_key_hint}</dd></div>
              <div><dt className="text-muted-foreground">Paybill payments by hand</dt><dd className="font-bold">{c.c2b_registered_at ? `Receiving since ${formatDate(c.c2b_registered_at)}` : "Not registered yet"}</dd></div>
            </dl>
            {c.last_error && <p className="text-sm text-destructive">Last error: {c.last_error}</p>}
            <CopyRow label="Confirmation URL" value={c.c2b_confirmation_url} />
            <CopyRow label="Validation URL" value={c.c2b_validation_url} />
            {canEdit && (
              <div className="flex flex-wrap gap-2">
                {!c.c2b_registered_at && c.status === "active" && (
                  <Button disabled={busy} onClick={() => run(() => mpesaConnectionRegisterC2b(), "Paybill payments will now be matched to invoices")}>
                    <CheckCircle2 aria-hidden="true" /> Receive Paybill payments
                  </Button>
                )}
                <Button variant="outline" onClick={() => setEditing(true)}>Change keys</Button>
                {c.status === "active" && <Button variant="ghost" className="text-destructive" disabled={busy} onClick={() => run(() => mpesaConnectionDisable(), "M-Pesa turned off")}>Turn off</Button>}
              </div>
            )}
          </div>
        )}
        {showForm && (
          <form
            className="grid gap-4 rounded-lg border bg-card p-4"
            onSubmit={async (e) => {
              e.preventDefault();
              const ok = await run(
                () => mpesaConnectionSave({ environment, shortcode_type: type, business_shortcode: shortcode, till_number: type === "till" ? till : undefined, consumer_key: key, consumer_secret: secret, passkey }),
                "M-Pesa connected",
              );
              if (ok) { setEditing(false); setKey(""); setSecret(""); setPasskey(""); }
            }}
          >
            <p className="text-sm text-muted-foreground">
              Create an app on the Safaricom developer portal (Daraja) for your shortcode, then copy its keys here. We check them with Safaricom before saving, and store them encrypted.
            </p>
            <div className="grid gap-4 sm:grid-cols-2">
              <Field label="Account">
                {(p) => (
                  <NativeSelect {...p} value={environment} onChange={(e) => setEnvironment(e.target.value as ConnectionInEnvironment)}>
                    <option value="production">Live (real money)</option>
                    <option value="sandbox">Safaricom sandbox (testing)</option>
                    <option value="simulator">Simulator (no Safaricom, for trying it out)</option>
                  </NativeSelect>
                )}
              </Field>
              <Field label="Type">
                {(p) => (
                  <NativeSelect {...p} value={type} onChange={(e) => setType(e.target.value as ConnectionInShortcodeType)}>
                    <option value="paybill">Paybill</option>
                    <option value="till">Buy Goods (Till)</option>
                  </NativeSelect>
                )}
              </Field>
              <Field label={type === "till" ? "Store number" : "Paybill number"}>{(p) => <Input {...p} inputMode="numeric" required value={shortcode} onChange={(e) => setShortcode(e.target.value.trim())} />}</Field>
              {type === "till" && <Field label="Till number">{(p) => <Input {...p} inputMode="numeric" required value={till} onChange={(e) => setTill(e.target.value.trim())} />}</Field>}
            </div>
            <Field label="Consumer key">{(p) => <Input {...p} required autoComplete="off" value={key} onChange={(e) => setKey(e.target.value)} />}</Field>
            <Field label="Consumer secret">{(p) => <Input {...p} type="password" required autoComplete="off" value={secret} onChange={(e) => setSecret(e.target.value)} />}</Field>
            <Field label="Passkey" hint="From Safaricom when your shortcode is enabled for payment prompts (Lipa na M-Pesa Online).">
              {(p) => <Input {...p} type="password" required autoComplete="off" value={passkey} onChange={(e) => setPasskey(e.target.value)} />}
            </Field>
            <div className="flex gap-2">
              <Button type="submit" disabled={busy}>{busy ? "Checking with Safaricom…" : "Connect M-Pesa"}</Button>
              {c && <Button type="button" variant="ghost" onClick={() => setEditing(false)}>Cancel</Button>}
            </div>
          </form>
        )}
        {!c && !canEdit && <p className="text-muted-foreground">M-Pesa is not connected yet. Ask the agency owner or an admin.</p>}
      </section>

      <section aria-labelledby="cards-heading" className="grid gap-2 rounded-lg border border-dashed p-4">
        <div className="flex items-center gap-2">
          <CreditCard className="size-5 text-muted-foreground" aria-hidden="true" />
          <h2 id="cards-heading" className="text-xl">Card payments</h2>
          <Badge variant="secondary">Coming soon</Badge>
        </div>
        <p className="text-sm text-muted-foreground">Visa and Mastercard payments from the invoice link are on the way.</p>
      </section>
    </div>
  );
}
