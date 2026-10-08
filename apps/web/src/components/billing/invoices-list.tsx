"use client";

import Link from "next/link";
import { useState } from "react";

import { BillingStatus } from "@/components/billing/status";
import { Skeleton } from "@/components/ui/skeleton";
import { useInvoicesList } from "@/lib/api/generated/billing/billing";
import type { InvoicesListParams } from "@/lib/api/generated/model";
import { formatDate, formatMoney } from "@/lib/format";
import { cn } from "@/lib/utils";

const FILTERS: { key: NonNullable<InvoicesListParams["status"]> | "all"; label: string }[] = [
  { key: "all", label: "All" },
  { key: "unpaid", label: "Unpaid" },
  { key: "overdue", label: "Overdue" },
  { key: "paid", label: "Paid" },
  { key: "draft", label: "Drafts" },
];

export function InvoicesList({ clientId }: { clientId?: string }) {
  const [status, setStatus] = useState<(typeof FILTERS)[number]["key"]>("all");
  const invoices = useInvoicesList({ ...(clientId ? { client_id: clientId } : {}), ...(status !== "all" ? { status } : {}) });
  return (
    <div className="grid gap-4">
      <div role="group" aria-label="Filter invoices" className="-mx-4 flex gap-1 overflow-x-auto px-4 sm:mx-0 sm:px-0">
        {FILTERS.map((f) => (
          <button key={f.key} type="button" aria-pressed={status === f.key} onClick={() => setStatus(f.key)}
            className={cn("rounded-full border px-3 py-1.5 text-sm whitespace-nowrap", status === f.key && "border-primary bg-primary text-primary-foreground")}>
            {f.label}
          </button>
        ))}
      </div>
      {!invoices.data ? <Skeleton className="h-40 w-full" /> : invoices.data.length === 0 ? (
        <p className="rounded-lg border border-dashed bg-card px-4 py-10 text-center text-muted-foreground">
          {status === "all" ? "No invoices yet. Start one from a client's page." : "No invoices match."}
        </p>
      ) : (
        <ul className="divide-y rounded-lg border bg-card" aria-label="Invoices">
          {invoices.data.map((i) => (
            <li key={i.id}>
              <Link href={`/invoices/${i.id}`} className="grid gap-1 px-4 py-3 hover:bg-accent sm:grid-cols-[minmax(0,2fr)_minmax(0,1fr)_auto] sm:items-center sm:gap-4">
                <span className="min-w-0">
                  <span className="block font-bold">{i.number ?? "Draft"}{clientId ? "" : ` · ${i.client.display_name}`}</span>
                  <span className="text-sm text-muted-foreground">
                    {i.issue_date ? `Issued ${formatDate(i.issue_date)}` : "Not issued"}{i.due_date && i.status !== "draft" ? ` · due ${formatDate(i.due_date)}` : ""}
                  </span>
                </span>
                <span className="tabular text-sm">
                  {formatMoney(i.total, i.currency)}
                  {Number(i.balance) > 0 && Number(i.paid) > 0 && <span className="block text-muted-foreground">{formatMoney(i.balance, i.currency)} left</span>}
                </span>
                <BillingStatus status={i.status} />
              </Link>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
