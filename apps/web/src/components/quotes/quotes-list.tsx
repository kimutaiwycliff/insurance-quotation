"use client";

import Link from "next/link";

import { QuoteStatus } from "@/components/quotes/status";
import { Skeleton } from "@/components/ui/skeleton";
import { useQuotesList } from "@/lib/api/generated/quotes/quotes";
import { formatDate, formatMoney } from "@/lib/format";

export function QuotesList({ clientId }: { clientId?: string }) {
  const quotes = useQuotesList(clientId ? { client_id: clientId } : undefined);
  if (!quotes.data) return <Skeleton className="h-48 w-full" />;
  if (quotes.data.length === 0) {
    return <p className="rounded-lg border border-dashed bg-card px-4 py-10 text-center text-muted-foreground">No quotes yet. Start one from a client&apos;s page.</p>;
  }
  return (
    <ul className="divide-y rounded-lg border bg-card" aria-label="Quotes">
      {quotes.data.map((q) => (
        <li key={q.id}>
          <Link href={`/quotes/${q.id}`} className="grid gap-1 px-4 py-3 hover:bg-accent sm:grid-cols-[minmax(0,2fr)_minmax(0,1fr)_auto] sm:items-center sm:gap-4">
            <span>
              <span className="block font-bold">{q.title}{q.number ? ` · ${q.number}` : ""}</span>
              <span className="text-sm text-muted-foreground">{q.client.display_name} · {q.options} {q.options === 1 ? "option" : "options"} · valid until {formatDate(q.valid_until)}</span>
            </span>
            <span className="tabular">{q.lowest_total ? `from ${formatMoney(q.lowest_total, q.currency)}` : ""}</span>
            <QuoteStatus status={q.status} />
          </Link>
        </li>
      ))}
    </ul>
  );
}
