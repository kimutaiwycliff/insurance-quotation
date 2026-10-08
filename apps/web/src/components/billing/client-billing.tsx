"use client";

import Link from "next/link";

import { InvoicesList } from "@/components/billing/invoices-list";
import { PaymentsList } from "@/components/billing/payments-list";
import { Button } from "@/components/ui/button";
import { useClientsAccount } from "@/lib/api/generated/billing/billing";
import { formatMoney } from "@/lib/format";

export function ClientBilling({ clientId }: { clientId: string }) {
  const account = useClientsAccount(clientId);
  return (
    <div className="grid gap-6">
      {account.data && (
        <dl className="grid grid-cols-2 gap-3 sm:max-w-md">
          <div className="rounded-lg border bg-card px-4 py-3"><dt className="text-sm text-muted-foreground">Owes you</dt><dd className="tabular font-heading text-2xl">{formatMoney(account.data.owed, account.data.currency)}</dd></div>
          <div className="rounded-lg border bg-card px-4 py-3"><dt className="text-sm text-muted-foreground">Credit on account</dt><dd className="tabular font-heading text-2xl">{formatMoney(account.data.credit, account.data.currency)}</dd></div>
        </dl>
      )}
      <div className="flex flex-wrap gap-2">
        <Button asChild variant="outline" size="sm"><Link href={`/invoices/new?client=${clientId}`}>New invoice</Link></Button>
        <Button asChild variant="outline" size="sm"><Link href={`/sales-quotes/new?client=${clientId}`}>New sales quote</Link></Button>
      </div>
      <InvoicesList clientId={clientId} />
      <section aria-labelledby="client-sales-quotes" className="grid gap-2">
        <h2 id="client-sales-quotes" className="text-xl">Sales quotes</h2>
        <InvoicesList clientId={clientId} kind="quote" />
      </section>
      <section aria-labelledby="client-payments" className="grid gap-2">
        <h2 id="client-payments" className="text-xl">Payments</h2>
        <PaymentsList clientId={clientId} />
      </section>
      <p className="text-sm text-muted-foreground"><Link href="/payments" className="hover:underline">All payments</Link></p>
    </div>
  );
}
