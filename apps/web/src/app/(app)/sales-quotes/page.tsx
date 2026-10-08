import Link from "next/link";

import { InvoicesList } from "@/components/billing/invoices-list";
import { Button } from "@/components/ui/button";

export const metadata = { title: "Sales quotes" };

export default function SalesQuotesPage() {
  return (
    <div className="grid gap-5">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h1 className="text-3xl">Sales quotes</h1>
          <p className="mt-1 text-muted-foreground">Quotations for goods and services. Start one from a client&apos;s Invoices tab.</p>
        </div>
        <div className="flex gap-2">
          <Button asChild variant="outline"><Link href="/invoices">Invoices</Link></Button>
          <Button asChild variant="outline"><Link href="/payments">Payments</Link></Button>
        </div>
      </div>
      <InvoicesList kind="quote" />
    </div>
  );
}
