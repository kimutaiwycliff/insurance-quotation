"use client";

import { useQueryClient } from "@tanstack/react-query";
import { Plus } from "lucide-react";
import Link from "next/link";
import { useMemo, useState } from "react";
import { toast } from "sonner";

import { Field, FormError } from "@/components/forms/field";
import { todayIso } from "@/components/policies/new-policy";
import { useCan } from "@/components/shell/me-context";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { NativeSelect } from "@/components/ui/native-select";
import {
  Sheet,
  SheetContent,
  SheetDescription,
  SheetHeader,
  SheetTitle,
} from "@/components/ui/sheet";
import { Skeleton } from "@/components/ui/skeleton";
import { Textarea } from "@/components/ui/textarea";
import {
  commissionReceiptsCreate,
  commissionReceiptsVoid,
  useCommissionReceiptsList,
  useCommissionsStatement,
  useCommissionsSummary,
} from "@/lib/api/generated/commissions/commissions";
import type { ReceiptOut, StatementRow, Summary } from "@/lib/api/generated/model";
import { formatDate, formatMoney, fractionToPercent, sumAmounts } from "@/lib/format";
import { ApiError, problemMessage } from "@/lib/problem";
import { cn } from "@/lib/utils";

const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];

/** Bar heights as whole percentages of the largest amount, computed from strings without float maths on money. */
function share(amount: string, max: string): number {
  const a = Number(amount.split(".")[0]);
  const m = Number(max.split(".")[0]);
  return m > 0 ? Math.max(Math.round((a / m) * 100), a > 0 ? 2 : 0) : 0;
}

function Figures({ summary }: { summary: Summary }) {
  const money = (a: string) => formatMoney(a, summary.currency);
  const items = [
    { label: `Expected on ${summary.year} policies`, value: money(summary.expected_net) },
    { label: `Received in ${summary.year}`, value: money(summary.received_net) },
    {
      label: "Still owed by insurers",
      value: money(summary.outstanding_net),
      urgent: Number(summary.outstanding_net) > 0,
    },
    { label: "WHT withheld (claim it on your tax return)", value: money(summary.wht) },
  ];
  return (
    <dl className="grid grid-cols-2 gap-3 lg:grid-cols-4">
      {items.map((i) => (
        <div key={i.label} className="bg-card rounded-lg border px-4 py-3">
          <dt className="text-muted-foreground text-sm">{i.label}</dt>
          <dd className={cn("tabular font-heading text-2xl", i.urgent && "text-destructive")}>
            {i.value}
          </dd>
        </div>
      ))}
    </dl>
  );
}

function MonthChart({ summary }: { summary: Summary }) {
  const max = summary.months.reduce((m, r) => {
    const big = Number(r.expected_net) > Number(r.received_net) ? r.expected_net : r.received_net;
    return Number(big) > Number(m) ? big : m;
  }, "0");
  return (
    <figure className="grid gap-2">
      <figcaption className="text-muted-foreground flex flex-wrap items-center gap-4 text-sm">
        <span>Net commission by month</span>
        <span className="flex items-center gap-1.5">
          <span aria-hidden="true" className="bg-maize size-3 rounded-sm" /> Expected
        </span>
        <span className="flex items-center gap-1.5">
          <span aria-hidden="true" className="bg-primary size-3 rounded-sm" /> Received
        </span>
      </figcaption>
      <ol className="grid h-40 grid-cols-12 items-end gap-1 border-b sm:gap-2">
        {summary.months.map((m, i) => (
          <li
            key={m.month}
            className="flex h-full items-end justify-center gap-0.5"
            aria-label={`${MONTHS[i]}: expected ${formatMoney(m.expected_net, summary.currency)}, received ${formatMoney(m.received_net, summary.currency)}`}
          >
            <span
              className="bg-maize w-1/2 max-w-3 rounded-t-sm"
              style={{ height: `${share(m.expected_net, max)}%` }}
            />
            <span
              className="bg-primary w-1/2 max-w-3 rounded-t-sm"
              style={{ height: `${share(m.received_net, max)}%` }}
            />
          </li>
        ))}
      </ol>
      <ol
        aria-hidden="true"
        className="text-muted-foreground grid grid-cols-12 gap-1 text-center text-xs sm:gap-2"
      >
        {MONTHS.map((m) => (
          <li key={m}>
            {m.slice(0, 1)}
            <span className="hidden sm:inline">{m.slice(1)}</span>
          </li>
        ))}
      </ol>
    </figure>
  );
}

function RecordReceipt({
  rows,
  open,
  onOpenChange,
  onDone,
}: {
  rows: StatementRow[];
  open: boolean;
  onOpenChange: (o: boolean) => void;
  onDone: () => Promise<unknown>;
}) {
  const insurers = useMemo(() => [...new Set(rows.map((r) => r.insurer_name))].sort(), [rows]);
  const [insurer, setInsurer] = useState("");
  const [receivedOn, setReceivedOn] = useState(todayIso());
  const [reference, setReference] = useState("");
  const [certificate, setCertificate] = useState("");
  const [lines, setLines] = useState<Record<string, { on: boolean; gross: string; wht: string }>>(
    {},
  );
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const current = insurer || insurers[0] || "";
  const ofInsurer = rows.filter(
    (r) => r.insurer_name === current && Number(r.outstanding.gross) > 0,
  );
  const line = (r: StatementRow) =>
    lines[r.policy_id] ?? { on: true, gross: r.outstanding.gross, wht: "" };
  const chosen = ofInsurer.filter((r) => line(r).on);
  const currency = ofInsurer[0]?.currency ?? "KES";

  async function submit() {
    setBusy(true);
    setError(null);
    try {
      await commissionReceiptsCreate({
        insurer_name: current,
        received_on: receivedOn,
        reference: reference || undefined,
        wht_certificate: certificate || undefined,
        lines: chosen.map((r) => ({
          policy_id: r.policy_id,
          gross: line(r).gross,
          wht: line(r).wht || undefined,
        })),
      });
      toast.success("Commission recorded");
      setLines({});
      onOpenChange(false);
      await onDone();
    } catch (e) {
      setError(e instanceof ApiError ? problemMessage(e.problem) : "Not saved. Try again.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <Sheet open={open} onOpenChange={onOpenChange}>
      <SheetContent className="w-full overflow-y-auto sm:max-w-2xl">
        <SheetHeader>
          <SheetTitle>Record commission received</SheetTitle>
          <SheetDescription>
            Copy the figures from the insurer&apos;s commission statement. WHT is worked out at your
            rate unless you enter the insurer&apos;s figure.
          </SheetDescription>
        </SheetHeader>
        <div className="grid gap-4 px-4 pb-8">
          <FormError message={error} />
          <div className="grid gap-4 sm:grid-cols-2">
            <Field label="Insurer">
              {(p) => (
                <NativeSelect
                  {...p}
                  value={current}
                  onChange={(e) => {
                    setInsurer(e.target.value);
                    setLines({});
                  }}
                >
                  {insurers.map((i) => (
                    <option key={i} value={i}>
                      {i}
                    </option>
                  ))}
                </NativeSelect>
              )}
            </Field>
            <Field label="Received on">
              {(p) => (
                <Input
                  {...p}
                  type="date"
                  value={receivedOn}
                  onChange={(e) => setReceivedOn(e.target.value)}
                />
              )}
            </Field>
            <Field label="Payment reference" optional>
              {(p) => (
                <Input {...p} value={reference} onChange={(e) => setReference(e.target.value)} />
              )}
            </Field>
            <Field label="WHT certificate number" optional>
              {(p) => (
                <Input
                  {...p}
                  value={certificate}
                  onChange={(e) => setCertificate(e.target.value)}
                />
              )}
            </Field>
          </div>
          {ofInsurer.length === 0 ? (
            <p className="text-muted-foreground">
              Nothing outstanding from {current || "this insurer"}.
            </p>
          ) : (
            <div
              tabIndex={0}
              role="region"
              aria-label="Policies paid by this receipt"
              className="overflow-x-auto rounded-lg border"
            >
              <table className="w-full min-w-[34rem] text-sm">
                <caption className="sr-only">Policies paid by this receipt</caption>
                <thead>
                  <tr className="text-muted-foreground border-b text-left">
                    <th className="px-3 py-2 font-normal">
                      <span className="sr-only">Include</span>
                    </th>
                    <th className="px-3 py-2 font-normal">Policy</th>
                    <th className="px-3 py-2 font-normal">Gross paid</th>
                    <th className="px-3 py-2 font-normal">WHT (optional)</th>
                  </tr>
                </thead>
                <tbody>
                  {ofInsurer.map((r) => {
                    const l = line(r);
                    const set = (patch: Partial<typeof l>) =>
                      setLines({ ...lines, [r.policy_id]: { ...l, ...patch } });
                    return (
                      <tr key={r.policy_id} className="border-b last:border-0">
                        <td className="px-3 py-2">
                          <input
                            type="checkbox"
                            className="size-4 accent-[var(--acacia)]"
                            aria-label={`Include ${r.client_name}, ${r.description}`}
                            checked={l.on}
                            onChange={(e) => set({ on: e.target.checked })}
                          />
                        </td>
                        <td className="px-3 py-2">
                          <span className="block font-bold">{r.client_name}</span>
                          <span className="text-muted-foreground">
                            {r.description}
                            {r.policy_number ? ` · ${r.policy_number}` : ""}
                          </span>
                        </td>
                        <td className="px-3 py-2">
                          <Input
                            aria-label={`Gross for ${r.description}`}
                            inputMode="decimal"
                            className="w-32"
                            value={l.gross}
                            onChange={(e) => set({ gross: e.target.value.replace(/[, ]/g, "") })}
                          />
                        </td>
                        <td className="px-3 py-2">
                          <Input
                            aria-label={`WHT for ${r.description}`}
                            inputMode="decimal"
                            className="w-28"
                            value={l.wht}
                            onChange={(e) => set({ wht: e.target.value.replace(/[, ]/g, "") })}
                          />
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          )}
          <p className="tabular">
            Gross on this receipt:{" "}
            <strong>{formatMoney(sumAmounts(chosen.map((r) => line(r).gross)), currency)}</strong>{" "}
            for {chosen.length} {chosen.length === 1 ? "policy" : "policies"}
          </p>
          <div>
            <Button size="lg" disabled={busy || chosen.length === 0} onClick={submit}>
              Record commission
            </Button>
          </div>
        </div>
      </SheetContent>
    </Sheet>
  );
}

function Receipts({ year, onChanged }: { year: number; onChanged: () => Promise<unknown> }) {
  const receipts = useCommissionReceiptsList({ year });
  const canManage = useCan("commission:manage");
  const [voiding, setVoiding] = useState<ReceiptOut | null>(null);
  const [reason, setReason] = useState("");
  if (!receipts.data) return <Skeleton className="h-24 w-full" />;
  if (receipts.data.length === 0)
    return <p className="text-muted-foreground">No commission recorded in {year}.</p>;
  return (
    <>
      <ul className="bg-card divide-y rounded-lg border">
        {receipts.data.map((r) => (
          <li
            key={r.id}
            className={cn(
              "grid gap-1 px-4 py-3 sm:grid-cols-[minmax(0,1fr)_auto_auto] sm:items-center sm:gap-4",
              r.voided_at && "text-muted-foreground",
            )}
          >
            <span>
              <span className="block font-bold">
                {r.insurer_name} · {formatDate(r.received_on)}
              </span>
              <span className="text-muted-foreground text-sm">
                {r.lines.length} {r.lines.length === 1 ? "policy" : "policies"}
                {r.reference ? ` · ${r.reference}` : ""}
                {r.wht_certificate ? ` · WHT cert ${r.wht_certificate}` : ""}
                {r.voided_at ? ` · Voided: ${r.void_reason}` : ""}
              </span>
            </span>
            <span className={cn("tabular", r.voided_at && "line-through")}>
              {formatMoney(r.net, r.currency)}{" "}
              <span className="text-muted-foreground text-sm">
                net of {formatMoney(r.wht, r.currency)} WHT
              </span>
            </span>
            {canManage && !r.voided_at ? (
              <Button size="sm" variant="ghost" onClick={() => setVoiding(r)}>
                Void
              </Button>
            ) : (
              <span />
            )}
          </li>
        ))}
      </ul>
      <Dialog open={voiding !== null} onOpenChange={(o) => !o && setVoiding(null)}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Void this receipt</DialogTitle>
            <DialogDescription>
              It stays in the history; its policies show the commission as owed again.
            </DialogDescription>
          </DialogHeader>
          <Textarea
            aria-label="Why void it"
            rows={2}
            value={reason}
            onChange={(e) => setReason(e.target.value)}
          />
          <DialogFooter>
            <Button
              variant="destructive"
              disabled={reason.trim().length < 2}
              onClick={async () => {
                await commissionReceiptsVoid(voiding!.id, { reason: reason.trim() });
                setVoiding(null);
                setReason("");
                await receipts.refetch();
                await onChanged();
              }}
            >
              Void receipt
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </>
  );
}

export function CommissionPage() {
  const queryClient = useQueryClient();
  const thisYear = new Date().getFullYear();
  const [year, setYear] = useState(thisYear);
  const [outstanding, setOutstanding] = useState(true);
  const [recording, setRecording] = useState(false);
  const canManage = useCan("commission:manage");
  const seesAll = useCan("commission:read:all");
  const summary = useCommissionsSummary({ year });
  const statement = useCommissionsStatement({ outstanding });
  const owed = useCommissionsStatement({ outstanding: true });
  const refresh = () =>
    queryClient.invalidateQueries({
      predicate: (q) => String(q.queryKey[0]).includes("/commission"),
    });

  return (
    <div className="grid gap-8">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h1 className="text-3xl">Commission</h1>
          <p className="text-muted-foreground mt-1">
            What insurers owe you on the policies you placed, and what they have paid.
          </p>
        </div>
        <div className="flex items-center gap-2">
          <NativeSelect
            aria-label="Year"
            value={String(year)}
            onChange={(e) => setYear(Number(e.target.value))}
            className="w-28"
          >
            {[thisYear, thisYear - 1, thisYear - 2].map((y) => (
              <option key={y} value={y}>
                {y}
              </option>
            ))}
          </NativeSelect>
          {canManage && (
            <Button onClick={() => setRecording(true)} disabled={!owed.data?.rows.length}>
              <Plus aria-hidden="true" /> Record commission
            </Button>
          )}
        </div>
      </div>

      {!summary.data ? (
        <Skeleton className="h-64 w-full" />
      ) : (
        <>
          <Figures summary={summary.data} />
          <MonthChart summary={summary.data} />
          {summary.data.insurers.length > 0 && (
            <section aria-labelledby="insurers-heading" className="grid gap-2">
              <h2 id="insurers-heading" className="text-xl">
                By insurer
              </h2>
              <div
                tabIndex={0}
                role="region"
                aria-label="Commission by insurer"
                className="bg-card overflow-x-auto rounded-lg border"
              >
                <table className="w-full min-w-[32rem] text-sm">
                  <thead>
                    <tr className="text-muted-foreground border-b text-left">
                      <th className="px-3 py-2 font-normal">Insurer</th>
                      <th className="px-3 py-2 text-right font-normal">Expected {year}</th>
                      <th className="px-3 py-2 text-right font-normal">Received {year}</th>
                      <th className="px-3 py-2 text-right font-normal">Still owed</th>
                    </tr>
                  </thead>
                  <tbody>
                    {summary.data.insurers.map((i) => (
                      <tr key={i.insurer_name} className="border-b last:border-0">
                        <th scope="row" className="px-3 py-2 text-left font-bold">
                          {i.insurer_name}
                        </th>
                        <td className="tabular px-3 py-2 text-right">
                          {formatMoney(i.expected_net, summary.data.currency)}
                        </td>
                        <td className="tabular px-3 py-2 text-right">
                          {formatMoney(i.received_net, summary.data.currency)}
                        </td>
                        <td
                          className={cn(
                            "tabular px-3 py-2 text-right",
                            Number(i.outstanding_net) > 0 && "font-bold",
                          )}
                        >
                          {formatMoney(i.outstanding_net, summary.data.currency)}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </section>
          )}
        </>
      )}

      <section aria-labelledby="statement-heading" className="grid gap-2">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <h2 id="statement-heading" className="text-xl">
            Policies
          </h2>
          <label className="flex items-center gap-2 text-sm">
            <input
              type="checkbox"
              className="size-4 accent-[var(--acacia)]"
              checked={outstanding}
              onChange={(e) => setOutstanding(e.target.checked)}
            />{" "}
            Only commission still owed
          </label>
        </div>
        {!statement.data ? (
          <Skeleton className="h-40 w-full" />
        ) : statement.data.rows.length === 0 ? (
          <p className="bg-card text-muted-foreground rounded-lg border border-dashed px-4 py-8 text-center">
            {outstanding
              ? "Insurers have paid everything they owe you."
              : "No policies with commission yet."}
          </p>
        ) : (
          <div
            tabIndex={0}
            role="region"
            aria-label="Commission by policy"
            className="bg-card overflow-x-auto rounded-lg border"
          >
            <table className="w-full min-w-[40rem] text-sm">
              <thead>
                <tr className="text-muted-foreground border-b text-left">
                  <th className="px-3 py-2 font-normal">Policy</th>
                  <th className="px-3 py-2 font-normal">Rate</th>
                  <th className="px-3 py-2 text-right font-normal">Expected (net)</th>
                  <th className="px-3 py-2 text-right font-normal">Received (net)</th>
                  <th className="px-3 py-2 text-right font-normal">Owed</th>
                </tr>
              </thead>
              <tbody>
                {statement.data.rows.map((r) => (
                  <tr key={r.policy_id} className="border-b last:border-0">
                    <td className="px-3 py-2">
                      <Link href={`/policies/${r.policy_id}`} className="font-bold hover:underline">
                        {r.client_name}
                      </Link>
                      <span className="text-muted-foreground block">
                        {r.description} · {r.insurer_name} · from {formatDate(r.start_date)}
                      </span>
                    </td>
                    <td className="tabular px-3 py-2">
                      {r.rate ? `${fractionToPercent(r.rate)}%` : ""}
                    </td>
                    <td className="tabular px-3 py-2 text-right">
                      {formatMoney(r.expected.net, r.currency)}
                    </td>
                    <td className="tabular px-3 py-2 text-right">
                      {formatMoney(r.received.net, r.currency)}
                    </td>
                    <td
                      className={cn(
                        "tabular px-3 py-2 text-right",
                        Number(r.outstanding.net) > 0 && "font-bold",
                      )}
                    >
                      {formatMoney(r.outstanding.net, r.currency)}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>

      {seesAll && (
        <section aria-labelledby="receipts-heading" className="grid gap-2">
          <h2 id="receipts-heading" className="text-xl">
            Received in {year}
          </h2>
          <Receipts year={year} onChanged={refresh} />
        </section>
      )}

      {seesAll && summary.data && summary.data.wht_certificates.length > 0 && (
        <section aria-labelledby="wht-heading" className="grid gap-2">
          <h2 id="wht-heading" className="text-xl">
            WHT certificates
          </h2>
          <p className="text-muted-foreground max-w-prose text-sm">
            Insurers withhold tax from your commission and give you a certificate. Check each one
            appears on iTax before you file.
          </p>
          <ul className="bg-card divide-y rounded-lg border">
            {summary.data.wht_certificates.map((c) => (
              <li
                key={c.receipt_id}
                className="flex flex-wrap justify-between gap-2 px-4 py-2 text-sm"
              >
                <span>
                  {c.insurer_name} · {formatDate(c.received_on)}
                </span>
                <span className={cn(!c.certificate && "text-destructive font-bold")}>
                  {c.certificate ?? "Certificate not received"}
                </span>
                <span className="tabular">{formatMoney(c.wht, summary.data.currency)}</span>
              </li>
            ))}
          </ul>
        </section>
      )}

      {canManage && owed.data && (
        <RecordReceipt
          rows={owed.data.rows}
          open={recording}
          onOpenChange={setRecording}
          onDone={refresh}
        />
      )}
    </div>
  );
}
