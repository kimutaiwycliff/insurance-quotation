"use client";

import { Search } from "lucide-react";
import Link from "next/link";
import { useState } from "react";

import { PolicyStatus } from "@/components/policies/status";
import { Input } from "@/components/ui/input";
import { Skeleton } from "@/components/ui/skeleton";
import { usePoliciesList } from "@/lib/api/generated/policies/policies";
import type { PoliciesListParams } from "@/lib/api/generated/model";
import { formatDate, formatMoney } from "@/lib/format";
import { cn } from "@/lib/utils";

const FILTERS: { key: NonNullable<PoliciesListParams["status"]> | "all"; label: string }[] = [
  { key: "all", label: "All" },
  { key: "active", label: "Active" },
  { key: "pending", label: "Awaiting cover" },
  { key: "expired", label: "Expired" },
  { key: "cancelled", label: "Cancelled" },
];

export function PoliciesList({ clientId }: { clientId?: string }) {
  const [status, setStatus] = useState<(typeof FILTERS)[number]["key"]>("all");
  const [q, setQ] = useState("");
  const policies = usePoliciesList({
    ...(clientId ? { client_id: clientId } : {}),
    ...(status !== "all" ? { status } : {}),
    ...(q.trim().length >= 2 ? { q: q.trim() } : {}),
  });

  return (
    <div className="grid gap-4">
      {!clientId && (
        <div className="flex flex-wrap items-center gap-3">
          <div role="group" aria-label="Filter by status" className="-mx-4 flex gap-1 overflow-x-auto px-4 sm:mx-0 sm:px-0">
            {FILTERS.map((f) => (
              <button key={f.key} type="button" aria-pressed={status === f.key} onClick={() => setStatus(f.key)}
                className={cn("rounded-full border px-3 py-1.5 text-sm whitespace-nowrap", status === f.key && "border-primary bg-primary text-primary-foreground")}>
                {f.label}
              </button>
            ))}
          </div>
          <label className="relative min-w-56 flex-1">
            <span className="sr-only">Search policies</span>
            <Search className="pointer-events-none absolute top-1/2 left-3 size-4 -translate-y-1/2 text-muted-foreground" aria-hidden="true" />
            <Input className="pl-9" placeholder="Policy number, vehicle or insurer" value={q} onChange={(e) => setQ(e.target.value)} />
          </label>
        </div>
      )}
      {!policies.data ? (
        <Skeleton className="h-48 w-full" />
      ) : policies.data.length === 0 ? (
        <p className="rounded-lg border border-dashed bg-card px-4 py-10 text-center text-muted-foreground">
          {status === "all" && !q ? "No policies yet. Turn an accepted quote into a policy, or add an existing one." : "No policies match."}
        </p>
      ) : (
        <ul className="divide-y rounded-lg border bg-card" aria-label="Policies">
          {policies.data.map((p) => (
            <li key={p.id}>
              <Link href={`/policies/${p.id}`} className="grid gap-1 px-4 py-3 hover:bg-accent sm:grid-cols-[minmax(0,2fr)_minmax(0,1fr)_auto] sm:items-center sm:gap-4">
                <span className="min-w-0">
                  <span className="block truncate font-bold">{p.description}</span>
                  <span className="text-sm text-muted-foreground">
                    {clientId ? "" : `${p.client.display_name} · `}{p.insurer_name}{p.policy_number ? ` · ${p.policy_number}` : ""} · ends {formatDate(p.end_date)}
                  </span>
                </span>
                <span className="tabular text-sm">
                  {formatMoney(p.total_premium, p.currency)}
                  {Number(p.balance) > 0 && p.status !== "cancelled" && <span className="block text-destructive">{formatMoney(p.balance, p.currency)} unpaid</span>}
                </span>
                <PolicyStatus status={p.status} />
              </Link>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
