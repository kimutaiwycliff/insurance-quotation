"use client";

import Link from "next/link";
import { useState } from "react";

import { BillingStatus } from "@/components/billing/status";
import { Skeleton } from "@/components/ui/skeleton";
import { useInvoicesList, useSalesQuotesList } from "@/lib/api/generated/billing/billing";
import { formatDate, formatMoney } from "@/lib/format";
import { cn } from "@/lib/utils";

type Kind = "invoice" | "quote";

const FILTERS: Record<Kind, { key: string; label: string }[]> = {
  invoice: [
    { key: "all", label: "All" },
    { key: "unpaid", label: "Unpaid" },
    { key: "overdue", label: "Overdue" },
    { key: "paid", label: "Paid" },
    { key: "draft", label: "Drafts" },
  ],
  quote: [
    { key: "all", label: "All" },
    { key: "awaiting", label: "Awaiting answer" },
    { key: "accepted", label: "Accepted" },
    { key: "invoiced", label: "Invoiced" },
    { key: "draft", label: "Drafts" },
  ],
};

/** Detail page of a billing document. */
export function docHref(kind: string, id: string): string {
  return kind === "quote" ? `/sales-quotes/${id}` : `/invoices/${id}`;
}

export function InvoicesList({ clientId, kind = "invoice" }: { clientId?: string; kind?: Kind }) {
  const [status, setStatus] = useState("all");
  const params = { ...(clientId ? { client_id: clientId } : {}), ...(status !== "all" ? { status } : {}) };
  const invoices = useInvoicesList(params as Parameters<typeof useInvoicesList>[0], { query: { enabled: kind === "invoice" } });
  const quotes = useSalesQuotesList(params as Parameters<typeof useSalesQuotesList>[0], { query: { enabled: kind === "quote" } });
  const list = kind === "quote" ? quotes : invoices;
  return (
    <div className="grid gap-4">
      <div role="group" aria-label="Filter invoices" className="-mx-4 flex gap-1 overflow-x-auto px-4 sm:mx-0 sm:px-0">
        {FILTERS[kind].map((f) => (
          <button key={f.key} type="button" aria-pressed={status === f.key} onClick={() => setStatus(f.key)}
            className={cn("rounded-full border px-3 py-1.5 text-sm whitespace-nowrap", status === f.key && "border-primary bg-primary text-primary-foreground")}>
            {f.label}
          </button>
        ))}
      </div>
      {!list.data ? <Skeleton className="h-40 w-full" /> : list.data.length === 0 ? (
        <p className="rounded-lg border border-dashed bg-card px-4 py-10 text-center text-muted-foreground">
          {status === "all" ? `No ${kind === "quote" ? "sales quotes" : "invoices"} yet. Start one from a client's page.` : "Nothing matches."}
        </p>
      ) : (
        <ul className="divide-y rounded-lg border bg-card" aria-label={kind === "quote" ? "Sales quotes" : "Invoices"}>
          {list.data.map((i) => (
            <li key={i.id}>
              <Link href={docHref(i.kind, i.id)} className="grid gap-1 px-4 py-3 hover:bg-accent sm:grid-cols-[minmax(0,2fr)_minmax(0,1fr)_auto] sm:items-center sm:gap-4">
                <span className="min-w-0">
                  <span className="block font-bold">{i.number ?? "Draft"}{clientId ? "" : ` · ${i.client.display_name}`}</span>
                  <span className="text-sm text-muted-foreground">
                    {i.issue_date ? `${kind === "quote" ? "Sent" : "Issued"} ${formatDate(i.issue_date)}` : kind === "quote" ? "Not sent" : "Not issued"}
                    {kind === "invoice" && i.due_date && i.status !== "draft" ? ` · due ${formatDate(i.due_date)}` : ""}
                    {kind === "quote" && i.valid_until ? ` · valid until ${formatDate(i.valid_until)}` : ""}
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
