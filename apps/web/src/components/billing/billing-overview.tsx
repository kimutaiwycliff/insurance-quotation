"use client";

import { useQueryClient } from "@tanstack/react-query";
import { BellRing } from "lucide-react";
import { useState } from "react";
import { toast } from "sonner";

import { FormError } from "@/components/forms/field";
import { useCan } from "@/components/shell/me-context";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Skeleton } from "@/components/ui/skeleton";
import { Switch } from "@/components/ui/switch";
import { ifMatch } from "@/lib/api/fetcher";
import { useBillingSummary } from "@/lib/api/generated/billing/billing";
import { getOrganizationGetQueryKey, organizationUpdate, useOrganizationGet } from "@/lib/api/generated/organization/organization";
import { formatMoney } from "@/lib/format";
import { ApiError, problemMessage } from "@/lib/problem";
import { cn } from "@/lib/utils";

function days(value: string): number[] | null {
  const parsed = value.split(/[,\s]+/).filter(Boolean).map(Number);
  return parsed.length && parsed.every((d) => Number.isInteger(d) && d > 0 && d <= 120) ? parsed : null;
}

function ReminderSettings({ open, onOpenChange }: { open: boolean; onOpenChange: (o: boolean) => void }) {
  const queryClient = useQueryClient();
  const org = useOrganizationGet();
  const [on, setOn] = useState<boolean | null>(null);
  const [before, setBefore] = useState<string | null>(null);
  const [after, setAfter] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  if (!org.data) return null;
  const o = org.data;
  const current = { on: on ?? o.billing_reminders, before: before ?? o.invoice_reminder_days_before.join(", "), after: after ?? o.invoice_reminder_days_after.join(", ") };

  async function save() {
    const b = days(current.before);
    const a = days(current.after);
    if (!b || !a) return setError("Enter whole numbers of days, separated by commas");
    try {
      const saved = await organizationUpdate({ billing_reminders: current.on, invoice_reminder_days_before: b, invoice_reminder_days_after: a }, ifMatch(o.version));
      queryClient.setQueryData(getOrganizationGetQueryKey(), saved);
      toast.success("Reminder settings saved");
      onOpenChange(false);
    } catch (e) {
      setError(e instanceof ApiError ? problemMessage(e.problem) : "Not saved. Try again.");
    }
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Payment reminders</DialogTitle>
          <DialogDescription>Each morning we email clients about invoices falling due or overdue, and quotes about to expire. Each reminder is sent once.</DialogDescription>
        </DialogHeader>
        <div className="grid gap-4">
          <FormError message={error} />
          <label className="flex items-center justify-between gap-4">
            <span className="font-bold">Send reminders to clients</span>
            <Switch checked={current.on} onCheckedChange={setOn} aria-label="Send reminders to clients" />
          </label>
          <label className="grid gap-1.5"><span className="text-sm font-bold">Days before the due date (and before a quote expires)</span><Input value={current.before} onChange={(e) => setBefore(e.target.value)} /></label>
          <label className="grid gap-1.5"><span className="text-sm font-bold">Days after the due date</span><Input value={current.after} onChange={(e) => setAfter(e.target.value)} /></label>
        </div>
        <DialogFooter><Button onClick={save}>Save</Button></DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

export function BillingOverview() {
  const summary = useBillingSummary();
  const canSettings = useCan("org:update");
  const [settings, setSettings] = useState(false);
  if (!summary.data) return <Skeleton className="h-32 w-full" />;
  const s = summary.data;
  const money = (a: string) => formatMoney(a, s.currency);
  const owed = s.ageing.filter((b) => Number(b.amount) > 0);
  return (
    <section aria-label="Invoicing overview" className="grid gap-3">
      <dl className="grid grid-cols-2 gap-3 lg:grid-cols-4">
        <div className="rounded-lg border bg-card px-4 py-3"><dt className="text-sm text-muted-foreground">Clients owe you</dt><dd className="tabular font-heading text-2xl">{money(s.outstanding)}</dd></div>
        <div className="rounded-lg border bg-card px-4 py-3"><dt className="text-sm text-muted-foreground">Overdue ({s.overdue_count})</dt><dd className={cn("tabular font-heading text-2xl", Number(s.overdue) > 0 && "text-destructive")}>{money(s.overdue)}</dd></div>
        <div className="rounded-lg border bg-card px-4 py-3"><dt className="text-sm text-muted-foreground">Collected this month</dt><dd className="tabular font-heading text-2xl">{money(s.collected_this_month)}</dd></div>
        <div className="rounded-lg border bg-card px-4 py-3"><dt className="text-sm text-muted-foreground">Quotes awaiting an answer ({s.quotes_awaiting})</dt><dd className="tabular font-heading text-2xl">{money(s.quotes_awaiting_total)}</dd></div>
      </dl>
      {owed.length > 0 && (
        <ul className="flex flex-wrap gap-x-6 gap-y-1 text-sm" aria-label="How late unpaid invoices are">
          {owed.map((b) => <li key={b.label}><span className="text-muted-foreground">{b.label}:</span> <span className="tabular font-bold">{money(b.amount)}</span> ({b.count})</li>)}
        </ul>
      )}
      {canSettings && <div><Button variant="outline" size="sm" onClick={() => setSettings(true)}><BellRing aria-hidden="true" /> Payment reminders</Button></div>}
      {canSettings && <ReminderSettings open={settings} onOpenChange={setSettings} />}
    </section>
  );
}
