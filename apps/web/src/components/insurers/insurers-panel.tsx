"use client";

import { useQueryClient } from "@tanstack/react-query";
import { Plus } from "lucide-react";
import { useState, type FormEvent } from "react";
import { toast } from "sonner";

import { PackBanner } from "@/components/insurers/pack-banner";
import { ProductForm } from "@/components/insurers/product-form";
import { Field, FormError } from "@/components/forms/field";
import { useCan } from "@/components/shell/me-context";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Sheet, SheetContent, SheetDescription, SheetHeader, SheetTitle } from "@/components/ui/sheet";
import { Skeleton } from "@/components/ui/skeleton";
import { ifMatch } from "@/lib/api/fetcher";
import {
  getInsurersListQueryKey,
  getProductsListQueryKey,
  insurersCreate,
  productsCreate,
  productsUpdate,
  useInsurersList,
  useJurisdictionPackGet,
  useProductsList,
} from "@/lib/api/generated/insurers/insurers";
import type { InsurerOut, ProductOut } from "@/lib/api/generated/model";
import { formatMoney, fractionToPercent } from "@/lib/format";
import { ApiError, problemMessage } from "@/lib/problem";

function AddInsurer({ onDone }: { onDone: () => Promise<void> }) {
  const [name, setName] = useState("");
  const [paybill, setPaybill] = useState("");
  const [hint, setHint] = useState("");
  const [error, setError] = useState<string | null>(null);
  async function submit(event: FormEvent) {
    event.preventDefault();
    try {
      await insurersCreate({ name, mpesa_paybill: paybill || undefined, payment_account_hint: hint || undefined });
      setName(""); setPaybill(""); setHint("");
      toast.success(`${name} added`);
      await onDone();
    } catch (e) {
      setError(e instanceof ApiError ? problemMessage(e.problem) : "The insurer was not added.");
    }
  }
  return (
    <form onSubmit={submit} className="grid gap-3 rounded-lg border bg-card p-4 sm:grid-cols-[minmax(0,1fr)_9rem_minmax(0,1fr)_auto] sm:items-end">
      <FormError message={error} />
      <Field label="Insurer">{(p) => <Input {...p} required value={name} onChange={(e) => setName(e.target.value)} placeholder="e.g. Example General Insurance" />}</Field>
      <Field label="M-Pesa Paybill" optional>{(p) => <Input {...p} inputMode="numeric" value={paybill} onChange={(e) => setPaybill(e.target.value)} />}</Field>
      <Field label="Account to use" optional>{(p) => <Input {...p} value={hint} onChange={(e) => setHint(e.target.value)} placeholder="e.g. Policy number" />}</Field>
      <Button type="submit" disabled={name.trim().length < 2}><Plus /> Add insurer</Button>
    </form>
  );
}

function describe(p: ProductOut): string {
  switch (p.rating_basis) {
    case "rate_on_sum_insured": return `${fractionToPercent(p.rate)}% of sum insured`;
    case "flat": return p.flat_premium ? formatMoney(p.flat_premium, p.currency) : "Fixed premium";
    case "per_member": return p.member_tiers.map((t) => `${t.label} ${formatMoney(t.amount, p.currency)}`).join(" · ");
    default: return "Entered per quote";
  }
}

export function InsurersPanel() {
  const queryClient = useQueryClient();
  const canManage = useCan("insurer:manage");
  const seesAll = useCan("commission:read:all");
  const seesOwn = useCan("commission:read:own");
  const showCommission = seesAll || seesOwn;
  const insurers = useInsurersList();
  const products = useProductsList();
  const pack = useJurisdictionPackGet();
  const [editing, setEditing] = useState<{ insurer: InsurerOut; product?: ProductOut } | null>(null);

  const refresh = async () => {
    await queryClient.invalidateQueries({ queryKey: getInsurersListQueryKey() });
    await queryClient.invalidateQueries({ queryKey: getProductsListQueryKey() });
  };
  const className = (code: string) => pack.data?.classes.find((c) => c.code === code)?.name ?? code;

  if (!insurers.data || !products.data || !pack.data) return <Skeleton className="h-80 w-full" />;
  return (
    <div className="grid gap-6">
      <PackBanner />
      {canManage && <AddInsurer onDone={refresh} />}
      {insurers.data.length === 0 && <p className="text-muted-foreground">Add the insurers you are appointed with, then their products and rates.</p>}
      {insurers.data.map((insurer) => {
        const own = products.data.filter((p) => p.insurer_id === insurer.id);
        return (
          <section key={insurer.id} aria-labelledby={`insurer-${insurer.id}`} className="rounded-lg border bg-card">
            <header className="flex flex-wrap items-center justify-between gap-2 border-b px-4 py-3">
              <div>
                <h3 id={`insurer-${insurer.id}`} className="text-lg">{insurer.name}</h3>
                {insurer.mpesa_paybill && <p className="text-sm text-muted-foreground">Paybill {insurer.mpesa_paybill}{insurer.payment_account_hint ? `, account: ${insurer.payment_account_hint}` : ""}</p>}
              </div>
              {canManage && <Button variant="outline" size="sm" onClick={() => setEditing({ insurer })}><Plus /> Add product</Button>}
            </header>
            {own.length === 0 ? <p className="px-4 py-3 text-sm text-muted-foreground">No products yet.</p> : (
              <ul className="divide-y">
                {own.map((p) => (
                  <li key={p.id} className="flex flex-wrap items-center gap-3 px-4 py-3">
                    <div className="min-w-0 flex-1">
                      <p className="font-bold">{p.name}</p>
                      <p className="text-sm text-muted-foreground">{className(p.class_code)} · {describe(p)}{Number(p.min_premium) > 0 ? ` · minimum ${formatMoney(p.min_premium, p.currency)}` : ""}</p>
                    </div>
                    {p.commission_rate_new && <Badge variant="secondary">Commission {fractionToPercent(p.commission_rate_new)}%</Badge>}
                    {canManage && <Button variant="ghost" size="sm" onClick={() => setEditing({ insurer, product: p })}>Edit</Button>}
                  </li>
                ))}
              </ul>
            )}
          </section>
        );
      })}
      <Sheet open={editing !== null} onOpenChange={(open) => !open && setEditing(null)}>
        <SheetContent className="w-full overflow-y-auto sm:max-w-xl">
          <SheetHeader>
            <SheetTitle>{editing?.product ? `Edit ${editing.product.name}` : `New product: ${editing?.insurer.name ?? ""}`}</SheetTitle>
            <SheetDescription className="sr-only">Product terms</SheetDescription>
          </SheetHeader>
          {editing && (
            <div className="px-4 pb-8">
              <ProductForm
                classes={pack.data.classes}
                initial={editing.product}
                showCommission={showCommission}
                onSubmit={async (body) => {
                  if (editing.product) {
                    await productsUpdate(editing.product.id, body, ifMatch(editing.product.version));
                  } else {
                    await productsCreate({ ...body, insurer_id: editing.insurer.id });
                  }
                  toast.success("Product saved");
                  setEditing(null);
                  await refresh();
                }}
              />
            </div>
          )}
        </SheetContent>
      </Sheet>
    </div>
  );
}
