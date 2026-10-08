import Link from "next/link";

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
        <Button asChild variant="outline"><Link href="/payments">Payments</Link></Button>
      </div>
      <InvoicesList />
    </div>
  );
}
