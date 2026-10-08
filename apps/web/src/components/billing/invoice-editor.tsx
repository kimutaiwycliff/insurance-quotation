"use client";

import { Plus, Trash2 } from "lucide-react";
import { useRouter } from "next/navigation";
import { useState, type FormEvent } from "react";

import { Field, FormError } from "@/components/forms/field";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { NativeSelect } from "@/components/ui/native-select";
import { Skeleton } from "@/components/ui/skeleton";
import { Textarea } from "@/components/ui/textarea";
import { ifMatch } from "@/lib/api/fetcher";
import { docHref } from "@/components/billing/invoices-list";
import { billingDocumentsUpdate, invoicesCreate, salesQuotesCreate } from "@/lib/api/generated/billing/billing";
import { useItemsList } from "@/lib/api/generated/catalog/catalog";
import { useClientsGet } from "@/lib/api/generated/clients/clients";
import { useJurisdictionPackGet } from "@/lib/api/generated/insurers/insurers";
import type { BillingDocumentOut, LineInput } from "@/lib/api/generated/model";
import { fractionToPercent, percentToFraction } from "@/lib/format";
import { ApiError, problemMessage } from "@/lib/problem";
import { randomId } from "@/lib/utils";

interface Row {
  key: string;
  itemId: string;
  description: string;
  quantity: string;
  price: string;
  discount: string;
  taxCode: string;
  section: string;
  optional: boolean;
}

function blank(taxCode: string): Row {
  return { key: randomId(), itemId: "", description: "", quantity: "1", price: "", discount: "", taxCode, section: "", optional: false };
}

export function InvoiceEditor({ clientId, draft, kind = "invoice" }: { clientId: string; draft?: BillingDocumentOut; kind?: "invoice" | "quote" }) {
  const isQuote = (draft?.kind ?? kind) === "quote";
  const router = useRouter();
  const client = useClientsGet(clientId);
  const items = useItemsList();
  const pack = useJurisdictionPackGet();
  const defaultCode = pack.data?.tax_codes.find((t) => t.kind === "vat")?.code ?? pack.data?.tax_codes[0]?.code ?? "";
  const [rows, setRows] = useState<Row[] | null>(
    draft
      ? draft.lines.map((l) => ({
          key: randomId(),
          itemId: l.item_id ?? "",
          description: l.description,
          quantity: l.quantity,
          price: l.unit_price,
          discount: Number(l.discount_rate) ? fractionToPercent(l.discount_rate) : "",
          taxCode: l.tax_code,
          section: l.section ?? "",
          optional: l.optional,
        }))
      : null,
  );
  const [inclusive, setInclusive] = useState(draft?.prices_include_tax ?? false);
  const [dueDays, setDueDays] = useState("14");
  const [validDays, setValidDays] = useState("30");
  const [reference, setReference] = useState(draft?.reference ?? "");
  const [notes, setNotes] = useState(draft?.notes ?? "");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  if (!client.data || !items.data || !pack.data) return <Skeleton className="h-96 w-full" />;
  const lines = rows ?? [blank(defaultCode)];
  const set = (key: string, patch: Partial<Row>) => setRows(lines.map((r) => (r.key === key ? { ...r, ...patch } : r)));
  const currency = draft?.currency ?? items.data[0]?.currency ?? "KES";

  function chooseItem(row: Row, itemId: string) {
    const item = items.data!.find((i) => i.id === itemId);
    set(row.key, item ? { itemId, description: item.name, price: item.unit_price, taxCode: item.tax_code } : { itemId: "" });
  }

  async function submit(event: FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError(null);
    const body: LineInput[] = lines.map((r) => ({
      item_id: r.itemId || undefined,
      description: r.description,
      quantity: r.quantity,
      unit_price: r.price,
      discount_rate: r.discount ? (percentToFraction(r.discount) ?? "0") : "0",
      tax_code: r.taxCode,
      section: isQuote ? r.section || undefined : undefined,
      optional: isQuote ? r.optional : false,
    }));
    try {
      const common = { lines: body, prices_include_tax: inclusive, reference: reference || undefined, notes: notes || undefined };
      const doc = draft
        ? await billingDocumentsUpdate(
            draft.id,
            { ...common, reference: reference || null, notes: notes || null, ...(isQuote ? { valid_days: Number(validDays) } : { due_in_days: Number(dueDays) }) },
            ifMatch(draft.version),
          )
        : isQuote
          ? await salesQuotesCreate({ client_id: clientId, ...common, valid_days: Number(validDays) || 30 })
          : await invoicesCreate({ client_id: clientId, ...common, due_in_days: Number(dueDays) || 0 });
      router.push(docHref(doc.kind, doc.id));
    } catch (e) {
      setError(e instanceof ApiError ? problemMessage(e.problem) : "The invoice was not saved. Try again.");
      setBusy(false);
    }
  }

  return (
    <form onSubmit={submit} className="grid gap-6">
      <div>
        <h1 className="text-3xl">{isQuote ? (draft ? "Edit draft quote" : "New sales quote") : draft ? "Edit draft invoice" : "New invoice"}</h1>
        <p className="mt-1 text-muted-foreground">
          For {client.data.display_name}. Totals and VAT are worked out when you save.
          {isQuote ? " Group lines under headings, and mark extras the client can choose." : ""}
        </p>
      </div>
      <FormError message={error} />
      <fieldset className="grid gap-3">
        <legend className="mb-1 text-sm font-bold">Lines</legend>
        {lines.map((row, index) => (
          <div key={row.key} className="grid gap-2 rounded-lg border bg-card p-3 sm:grid-cols-[minmax(0,2fr)_5rem_8rem_5rem_9rem_auto] sm:items-end">
            <div className="grid gap-2">
              {isQuote && <Input aria-label={`Heading for line ${index + 1}`} placeholder="Heading (optional), e.g. Design" value={row.section} onChange={(e) => set(row.key, { section: e.target.value })} />}
              {items.data.length > 0 && (
                <NativeSelect aria-label={`Item for line ${index + 1}`} value={row.itemId} onChange={(e) => chooseItem(row, e.target.value)}>
                  <option value="">Type a description</option>
                  {items.data.map((i) => <option key={i.id} value={i.id}>{i.name}</option>)}
                </NativeSelect>
              )}
              <Input aria-label={`Description for line ${index + 1}`} required placeholder="What you are charging for" value={row.description} onChange={(e) => set(row.key, { description: e.target.value })} />
              {isQuote && (
                <label className="flex items-center gap-2 text-sm">
                  <input type="checkbox" className="size-4 accent-[var(--acacia)]" checked={row.optional} onChange={(e) => set(row.key, { optional: e.target.checked })} />
                  Optional extra (the client chooses; not in the total)
                </label>
              )}
            </div>
            <Input aria-label={`Quantity for line ${index + 1}`} inputMode="decimal" required value={row.quantity} onChange={(e) => set(row.key, { quantity: e.target.value })} />
            <Input aria-label={`Price for line ${index + 1}`} inputMode="decimal" required placeholder="Price" value={row.price} onChange={(e) => set(row.key, { price: e.target.value.replace(/[, ]/g, "") })} />
            <Input aria-label={`Discount % for line ${index + 1}`} inputMode="decimal" placeholder="Disc. %" value={row.discount} onChange={(e) => set(row.key, { discount: e.target.value })} />
            <NativeSelect aria-label={`Tax for line ${index + 1}`} value={row.taxCode} onChange={(e) => set(row.key, { taxCode: e.target.value })}>
              {pack.data.tax_codes.map((t) => <option key={t.code} value={t.code}>{t.name}</option>)}
            </NativeSelect>
            <Button type="button" variant="ghost" size="icon" aria-label={`Remove line ${index + 1}`} disabled={lines.length === 1} onClick={() => setRows(lines.filter((r) => r.key !== row.key))}><Trash2 /></Button>
          </div>
        ))}
        <Button type="button" variant="outline" size="sm" className="justify-self-start" onClick={() => setRows([...lines, blank(defaultCode)])}><Plus /> Add line</Button>
      </fieldset>
      <label className="flex items-center gap-2">
        <input type="checkbox" className="size-4 accent-[var(--acacia)]" checked={inclusive} onChange={(e) => setInclusive(e.target.checked)} />
        Prices already include VAT
      </label>
      <div className="grid gap-4 sm:grid-cols-3">
        {isQuote ? (
          <Field label="Valid for (days)">{(p) => <Input {...p} type="number" min={1} max={180} value={validDays} onChange={(e) => setValidDays(e.target.value)} />}</Field>
        ) : (
          <Field label="Due in (days)">{(p) => <Input {...p} type="number" min={0} max={365} value={dueDays} onChange={(e) => setDueDays(e.target.value)} />}</Field>
        )}
        <Field label="Client's order number" optional>{(p) => <Input {...p} value={reference} onChange={(e) => setReference(e.target.value)} />}</Field>
      </div>
      <Field label="Note to the client" optional>{(p) => <Textarea {...p} rows={2} value={notes} onChange={(e) => setNotes(e.target.value)} />}</Field>
      <p className="text-sm text-muted-foreground">Amounts in {currency}.</p>
      <div><Button type="submit" size="lg" disabled={busy}>{draft ? "Save draft" : isQuote ? "Save draft quote" : "Save draft invoice"}</Button></div>
    </form>
  );
}
