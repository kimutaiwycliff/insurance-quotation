"use client";

import { useQueryClient } from "@tanstack/react-query";
import { ExternalLink } from "lucide-react";
import { useState } from "react";
import { toast } from "sonner";

import { Field, FormError } from "@/components/forms/field";
import { useCan } from "@/components/shell/me-context";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Switch } from "@/components/ui/switch";
import { ifMatch } from "@/lib/api/fetcher";
import { billingDocumentsEtims } from "@/lib/api/generated/billing/billing";
import type { BillingDocumentOut } from "@/lib/api/generated/model";
import { getOrganizationGetQueryKey, organizationUpdate, useOrganizationGet } from "@/lib/api/generated/organization/organization";
import { formatDate } from "@/lib/format";
import { ApiError, problemMessage } from "@/lib/problem";

/** Settings → Tax: the optional eTIMS switch (ADR-0017). */
export function TaxSettings() {
  const queryClient = useQueryClient();
  const org = useOrganizationGet();
  const canEdit = useCan("org:update");
  if (!org.data) return null;
  const o = org.data;
  return (
    <div className="grid max-w-2xl gap-4">
      <label className="flex items-start justify-between gap-6 rounded-lg border bg-card p-4">
        <span>
          <span className="block font-bold">Record eTIMS on invoices</span>
          <span className="text-sm text-muted-foreground">
            After you issue an invoice or credit note, enter the CU invoice number (and the verification link) from your own eTIMS tool. We print them on the PDF and on the client&apos;s page.
          </span>
        </span>
        <Switch
          checked={o.etims_enabled}
          disabled={!canEdit}
          aria-label="Record eTIMS on invoices"
          onCheckedChange={async (value) => {
            try {
              const saved = await organizationUpdate({ etims_enabled: value }, ifMatch(o.version));
              queryClient.setQueryData(getOrganizationGetQueryKey(), saved);
              toast.success(value ? "eTIMS turned on" : "eTIMS turned off");
            } catch (e) {
              toast.error(e instanceof ApiError ? problemMessage(e.problem) : "Not saved. Try again.");
            }
          }}
        />
      </label>
      <p className="text-sm text-muted-foreground">
        With eTIMS off, documents carry no eTIMS details and you remain responsible for KRA compliance through your own tools. Sending invoices to KRA automatically is planned for later.
      </p>
    </div>
  );
}

/** eTIMS details on an issued invoice or credit note: shown, or recorded by someone who may issue. */
export function EtimsPanel({ doc, onSaved }: { doc: BillingDocumentOut; onSaved: () => Promise<unknown> }) {
  const org = useOrganizationGet();
  const canIssue = useCan("invoice:issue");
  const [editing, setEditing] = useState(false);
  const [cu, setCu] = useState(doc.etims_cu_invoice_number ?? "");
  const [url, setUrl] = useState(doc.etims_verification_url ?? "");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  if (!org.data?.etims_enabled || doc.kind === "quote" || doc.status === "draft" || doc.status === "void") return null;
  const recorded = Boolean(doc.etims_cu_invoice_number);

  async function save() {
    setBusy(true);
    setError(null);
    try {
      await billingDocumentsEtims(doc.id, { cu_invoice_number: cu, verification_url: url || undefined });
      await onSaved();
      toast.success("eTIMS details saved");
      setEditing(false);
    } catch (e) {
      setError(e instanceof ApiError ? problemMessage(e.problem) : "Not saved. Try again.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <section aria-labelledby="etims-heading" className={`grid gap-3 rounded-lg border p-4 ${recorded ? "bg-card" : "border-maize"}`}>
      <h2 id="etims-heading" className="text-xl">KRA eTIMS</h2>
      {recorded && !editing ? (
        <div className="flex flex-wrap items-center gap-x-6 gap-y-2 text-sm">
          <span>CU invoice no. <strong className="tabular">{doc.etims_cu_invoice_number}</strong></span>
          {doc.etims_verification_url && (
            <a href={doc.etims_verification_url} target="_blank" rel="noopener noreferrer" className="inline-flex items-center gap-1 text-primary hover:underline">
              Verify on KRA <ExternalLink className="size-4" aria-hidden="true" />
            </a>
          )}
          {doc.etims_recorded_at && <span className="text-muted-foreground">Recorded {formatDate(doc.etims_recorded_at)}</span>}
          {canIssue && <Button size="sm" variant="ghost" onClick={() => setEditing(true)}>Correct</Button>}
        </div>
      ) : canIssue ? (
        <div className="grid gap-3">
          {!recorded && <p className="text-sm text-muted-foreground">Submit this document in your eTIMS tool, then enter what it returned.</p>}
          <FormError message={error} />
          <div className="grid gap-3 sm:grid-cols-2">
            <Field label="CU invoice number">{(p) => <Input {...p} value={cu} onChange={(e) => setCu(e.target.value)} placeholder="KRAMW0012345678901" />}</Field>
            <Field label="Verification link" optional>{(p) => <Input {...p} type="url" value={url} onChange={(e) => setUrl(e.target.value)} placeholder="https://etims.kra.go.ke/…" />}</Field>
          </div>
          <div className="flex gap-2">
            <Button size="sm" disabled={busy || cu.trim().length < 6} onClick={save}>Save eTIMS details</Button>
            {editing && <Button size="sm" variant="ghost" onClick={() => setEditing(false)}>Cancel</Button>}
          </div>
        </div>
      ) : (
        <p className="text-sm text-muted-foreground">Not recorded yet.</p>
      )}
    </section>
  );
}
