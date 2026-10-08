"use client";

import { useQueryClient } from "@tanstack/react-query";
import { Plus } from "lucide-react";
import { useState } from "react";
import { toast } from "sonner";

import { Field, FormError } from "@/components/forms/field";
import { useCan } from "@/components/shell/me-context";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { NativeSelect } from "@/components/ui/native-select";
import { Skeleton } from "@/components/ui/skeleton";
import { ifMatch } from "@/lib/api/fetcher";
import { getItemsListQueryKey, itemsCreate, itemsUpdate, useItemsList } from "@/lib/api/generated/catalog/catalog";
import { useJurisdictionPackGet } from "@/lib/api/generated/insurers/insurers";
import type { ItemOut } from "@/lib/api/generated/model";
import { formatMoney } from "@/lib/format";
import { ApiError, problemMessage } from "@/lib/problem";

function ItemDialog({ item, open, onOpenChange }: { item: ItemOut | null; open: boolean; onOpenChange: (o: boolean) => void }) {
  const queryClient = useQueryClient();
  const pack = useJurisdictionPackGet();
  const [name, setName] = useState(item?.name ?? "");
  const [unit, setUnit] = useState(item?.unit ?? "");
  const [price, setPrice] = useState(item?.unit_price ?? "");
  const [taxCode, setTaxCode] = useState(item?.tax_code ?? "");
  const [error, setError] = useState<string | null>(null);
  const codes = pack.data?.tax_codes ?? [];
  const code = taxCode || codes[0]?.code || "";

  async function save() {
    setError(null);
    try {
      if (item) await itemsUpdate(item.id, { name, unit: unit || null, unit_price: price, tax_code: code }, ifMatch(item.version));
      else await itemsCreate({ name, unit: unit || undefined, unit_price: price, tax_code: code });
      await queryClient.invalidateQueries({ queryKey: getItemsListQueryKey() });
      toast.success("Item saved");
      onOpenChange(false);
    } catch (e) {
      setError(e instanceof ApiError ? problemMessage(e.problem) : "Not saved. Try again.");
    }
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>{item ? "Edit item" : "Add item"}</DialogTitle>
          <DialogDescription>Something you sell, with its usual price. You can change the price on each invoice.</DialogDescription>
        </DialogHeader>
        <div className="grid gap-4">
          <FormError message={error} />
          <Field label="Name">{(p) => <Input {...p} value={name} onChange={(e) => setName(e.target.value)} />}</Field>
          <div className="grid gap-4 sm:grid-cols-2">
            <Field label="Price">{(p) => <Input {...p} inputMode="decimal" value={price} onChange={(e) => setPrice(e.target.value.replace(/[, ]/g, ""))} />}</Field>
            <Field label="Unit" optional hint="e.g. hour, piece, month">{(p) => <Input {...p} value={unit} onChange={(e) => setUnit(e.target.value)} />}</Field>
          </div>
          <Field label="Tax">
            {(p) => <NativeSelect {...p} value={code} onChange={(e) => setTaxCode(e.target.value)}>{codes.map((c) => <option key={c.code} value={c.code}>{c.name}</option>)}</NativeSelect>}
          </Field>
        </div>
        <DialogFooter><Button onClick={save} disabled={!name.trim() || !price}>Save item</Button></DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

export function ItemsPanel() {
  const items = useItemsList({ include_inactive: true });
  const canManage = useCan("catalog:manage");
  const [editing, setEditing] = useState<ItemOut | null | undefined>(undefined);
  if (!items.data) return <Skeleton className="h-40 w-full" />;
  return (
    <div className="grid gap-4">
      {canManage && <div><Button onClick={() => setEditing(null)}><Plus aria-hidden="true" /> Add item</Button></div>}
      {items.data.length === 0 ? (
        <p className="rounded-lg border border-dashed bg-card px-4 py-8 text-center text-muted-foreground">No items yet. Add the products and services you invoice most often.</p>
      ) : (
        <ul className="divide-y rounded-lg border bg-card" aria-label="Items">
          {items.data.map((item) => (
            <li key={item.id} className="flex flex-wrap items-center gap-3 px-4 py-3">
              <span className="min-w-0 flex-1">
                <span className="block font-bold">{item.name}{!item.active && <span className="ml-2 text-sm font-normal text-muted-foreground">(hidden)</span>}</span>
                <span className="text-sm text-muted-foreground">{item.tax_code.replace(/_/g, " ")}{item.unit ? ` · per ${item.unit}` : ""}</span>
              </span>
              <span className="tabular">{formatMoney(item.unit_price, item.currency)}</span>
              {canManage && <Button variant="ghost" size="sm" onClick={() => setEditing(item)}>Edit</Button>}
            </li>
          ))}
        </ul>
      )}
      {editing !== undefined && <ItemDialog key={editing?.id ?? "new"} item={editing} open onOpenChange={(o) => !o && setEditing(undefined)} />}
    </div>
  );
}
