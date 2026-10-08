"use client";

import { FileUp } from "lucide-react";
import Link from "next/link";
import { useState } from "react";

import { FormError } from "@/components/forms/field";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { NativeSelect } from "@/components/ui/native-select";
import { importsPoliciesPreview, importsPoliciesRun } from "@/lib/api/generated/imports/imports";
import { useOrganizationGet } from "@/lib/api/generated/organization/organization";
import type { ImportPreview, ImportResult } from "@/lib/api/generated/model";
import { formatDate, formatMoney } from "@/lib/format";
import { ApiError, problemMessage } from "@/lib/problem";
import { cn } from "@/lib/utils";

const MAX_BYTES = 2_000_000;

export function ImportBook() {
  const [file, setFile] = useState<{ name: string; text: string } | null>(null);
  const [assumePaid, setAssumePaid] = useState(true);
  const [mapping, setMapping] = useState<Record<string, string> | null>(null);
  const [preview, setPreview] = useState<ImportPreview | null>(null);
  const [skipErrors, setSkipErrors] = useState(false);
  const [result, setResult] = useState<ImportResult | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const currency = useOrganizationGet().data?.default_currency ?? "KES";

  async function check(
    next: { name: string; text: string } = file!,
    map: Record<string, string> | null = mapping,
  ) {
    setBusy(true);
    setError(null);
    try {
      const out = await importsPoliciesPreview({
        filename: next.name,
        csv: next.text,
        mapping: map ?? undefined,
        assume_paid: assumePaid,
      });
      setPreview(out);
      setMapping(out.mapping);
    } catch (e) {
      setPreview(null);
      setError(
        e instanceof ApiError
          ? problemMessage(e.problem)
          : "The file could not be read. Try again.",
      );
    } finally {
      setBusy(false);
    }
  }

  async function choose(f: File | undefined) {
    if (!f) return;
    if (f.size > MAX_BYTES)
      return setError("The file is larger than 2 MB. Split it into smaller files.");
    if (!/\.csv$/i.test(f.name))
      return setError("Choose a .csv file. In Excel: File, Save As, then 'CSV UTF-8'.");
    const next = { name: f.name, text: await f.text() };
    setFile(next);
    setResult(null);
    setMapping(null);
    await check(next, null);
  }

  async function run() {
    if (!file || !preview) return;
    setBusy(true);
    setError(null);
    try {
      setResult(
        await importsPoliciesRun({
          filename: file.name,
          csv: file.text,
          mapping: mapping ?? undefined,
          assume_paid: assumePaid,
          skip_errors: skipErrors,
        }),
      );
    } catch (e) {
      setError(
        e instanceof ApiError ? problemMessage(e.problem) : "Nothing was imported. Try again.",
      );
    } finally {
      setBusy(false);
    }
  }

  if (result) {
    return (
      <div className="grid max-w-2xl gap-4">
        <h1 className="text-3xl">Book imported</h1>
        <p className="text-lg">
          {result.policies_created} {result.policies_created === 1 ? "policy" : "policies"} added,{" "}
          {result.clients_created} new {result.clients_created === 1 ? "client" : "clients"}
          {result.clients_matched
            ? `, ${result.clients_matched} matched to clients you already had`
            : ""}
          .{result.rows_skipped ? ` ${result.rows_skipped} rows were left out.` : ""}
        </p>
        <div className="flex flex-wrap gap-2">
          <Button asChild>
            <Link href="/renewals">See renewals</Link>
          </Button>
          <Button asChild variant="outline">
            <Link href="/policies">All policies</Link>
          </Button>
        </div>
      </div>
    );
  }

  const rows = preview
    ? [...preview.rows].sort(
        (a, b) => Number(a.status === "ok") - Number(b.status === "ok") || a.line - b.line,
      )
    : [];
  return (
    <div className="grid gap-6">
      <div>
        <h1 className="text-3xl">Import your book</h1>
        <p className="text-muted-foreground mt-1 max-w-prose">
          Bring in the policies you already look after from a spreadsheet: one row per policy, with
          the client, insurer, class, start date and premium. Save it from Excel or Google Sheets as
          CSV. You will see every row before anything is saved.
        </p>
      </div>
      <FormError message={error} />
      <div className="flex flex-wrap items-center gap-4">
        <label className="bg-card hover:border-primary focus-within:ring-ring inline-flex cursor-pointer items-center gap-2 rounded-md border px-4 py-2 font-bold focus-within:ring-2">
          <FileUp className="size-5" aria-hidden="true" />{" "}
          {file ? "Choose another file" : "Choose CSV file"}
          <input
            type="file"
            accept=".csv,text/csv"
            className="sr-only"
            onChange={(e) => choose(e.target.files?.[0])}
          />
        </label>
        {file && <span className="text-muted-foreground">{file.name}</span>}
        <label className="flex items-center gap-2">
          <input
            type="checkbox"
            className="size-4 accent-[var(--acacia)]"
            checked={assumePaid}
            onChange={(e) => setAssumePaid(e.target.checked)}
          />
          Clients have paid these premiums
        </label>
      </div>

      {preview && (
        <>
          <section aria-labelledby="columns-heading" className="grid gap-2">
            <h2 id="columns-heading" className="text-xl">
              Columns
            </h2>
            <p className="text-muted-foreground text-sm">
              We matched your headings where we could. Check them, and choose the ones we missed.
            </p>
            <div className="grid gap-2 sm:grid-cols-2 lg:grid-cols-3">
              {preview.fields.map((f) => (
                <label key={f.key} className="grid gap-1 text-sm">
                  <span className="font-bold">
                    {f.label}
                    {f.required ? "" : " (optional)"}
                  </span>
                  <NativeSelect
                    value={mapping?.[f.key] ?? ""}
                    onChange={(e) => {
                      const next = { ...(mapping ?? {}) };
                      if (e.target.value) next[f.key] = e.target.value;
                      else delete next[f.key];
                      setMapping(next);
                    }}
                  >
                    <option value="">Not in my file</option>
                    {preview.columns.map((c) => (
                      <option key={c} value={c}>
                        {c}
                      </option>
                    ))}
                  </NativeSelect>
                </label>
              ))}
            </div>
            <div>
              <Button variant="outline" disabled={busy} onClick={() => check()}>
                Check again
              </Button>
            </div>
          </section>

          {preview.problems.length > 0 ? (
            <ul className="border-destructive/40 text-destructive grid gap-1 rounded-md border px-4 py-3">
              {preview.problems.map((p) => (
                <li key={p}>{p}</li>
              ))}
            </ul>
          ) : (
            <section aria-labelledby="rows-heading" className="grid gap-3">
              <h2 id="rows-heading" className="text-xl">
                Rows
              </h2>
              <p>
                <strong>{preview.ok}</strong> ready ({preview.new_clients} new{" "}
                {preview.new_clients === 1 ? "client" : "clients"}, {preview.matched_clients}{" "}
                already in your book)
                {preview.errors > 0 && (
                  <>
                    , <strong className="text-destructive">{preview.errors}</strong> with errors
                  </>
                )}
                {preview.skipped > 0 && <>, {preview.skipped} already imported</>}.
              </p>
              <div
                tabIndex={0}
                role="region"
                aria-label="Rows to import"
                className="bg-card max-h-[28rem] overflow-auto rounded-lg border"
              >
                <table className="w-full min-w-[44rem] text-sm">
                  <thead className="bg-card sticky top-0">
                    <tr className="text-muted-foreground border-b text-left">
                      <th className="px-3 py-2 font-normal">Line</th>
                      <th className="px-3 py-2 font-normal">Client</th>
                      <th className="px-3 py-2 font-normal">Policy</th>
                      <th className="px-3 py-2 font-normal">Cover</th>
                      <th className="px-3 py-2 text-right font-normal">Premium</th>
                      <th className="px-3 py-2 font-normal">Check</th>
                    </tr>
                  </thead>
                  <tbody>
                    {rows.slice(0, 300).map((r) => (
                      <tr
                        key={r.line}
                        className={cn(
                          "border-b align-top last:border-0",
                          r.status === "error" && "bg-destructive/5",
                        )}
                      >
                        <td className="tabular px-3 py-2">{r.line}</td>
                        <td className="px-3 py-2">
                          {r.client_name}
                          {r.client_action && (
                            <span className="text-muted-foreground block text-xs">
                              {r.client_action === "match" ? "Existing client" : "New client"}
                            </span>
                          )}
                        </td>
                        <td className="px-3 py-2">
                          {r.insurer}
                          {r.policy_number ? ` · ${r.policy_number}` : ""}
                          <span className="text-muted-foreground block text-xs">
                            {r.description}
                          </span>
                        </td>
                        <td className="px-3 py-2 whitespace-nowrap">
                          {r.start_date ? formatDate(r.start_date) : ""}
                          {r.end_date ? ` to ${formatDate(r.end_date)}` : ""}
                        </td>
                        <td className="tabular px-3 py-2 text-right">
                          {r.premium ? formatMoney(r.premium, currency) : ""}
                        </td>
                        <td className="px-3 py-2">
                          <Badge
                            variant={
                              r.status === "ok"
                                ? "default"
                                : r.status === "error"
                                  ? "destructive"
                                  : "secondary"
                            }
                          >
                            {r.status === "ok"
                              ? "Ready"
                              : r.status === "error"
                                ? "Error"
                                : "Skipped"}
                          </Badge>
                          {r.messages.map((m) => (
                            <span key={m} className="mt-1 block text-xs">
                              {m}
                            </span>
                          ))}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
              {preview.errors > 0 && (
                <label className="flex items-center gap-2">
                  <input
                    type="checkbox"
                    className="size-4 accent-[var(--acacia)]"
                    checked={skipErrors}
                    onChange={(e) => setSkipErrors(e.target.checked)}
                  />
                  Import the {preview.ok} ready rows and leave out the rows with errors
                </label>
              )}
              <div>
                <Button
                  size="lg"
                  disabled={busy || preview.ok === 0 || (preview.errors > 0 && !skipErrors)}
                  onClick={run}
                >
                  Import {preview.ok} {preview.ok === 1 ? "policy" : "policies"}
                </Button>
              </div>
            </section>
          )}
        </>
      )}
    </div>
  );
}
