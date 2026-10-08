import Link from "next/link";

import { BillingOverview } from "@/components/billing/billing-overview";
import { InvoicesList } from "@/components/billing/invoices-list";
import { Button } from "@/components/ui/button";

export const metadata = { title: "Invoices" };

export default function InvoicesPage() {
  return (
    <div className="grid gap-5">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h1 className="text-3xl">Invoices</h1>
          <p className="mt-1 text-muted-foreground">To start an invoice, open the client and choose New invoice.</p>
        </div>
        <div className="flex gap-2">
          <Button asChild variant="outline"><Link href="/sales-quotes">Sales quotes</Link></Button>
          <Button asChild variant="outline"><Link href="/payments">Payments</Link></Button>
        </div>
      </div>
      <BillingOverview />
      <InvoicesList />
    </div>
  );
}
