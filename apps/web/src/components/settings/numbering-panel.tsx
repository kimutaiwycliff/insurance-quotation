"use client";

import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useTranslations } from "next-intl";
import { useState } from "react";
import { toast } from "sonner";

import { Field } from "@/components/forms/field";
import { useCan } from "@/components/shell/me-context";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { NativeSelect } from "@/components/ui/native-select";
import { Skeleton } from "@/components/ui/skeleton";
import { ifMatch } from "@/lib/api/fetcher";
import type { SchemeOut } from "@/lib/api/generated/model";
import {
  getNumberingSchemesListQueryKey,
  numberingSchemesPreview,
  numberingSchemesUpdate,
  useNumberingSchemesList,
} from "@/lib/api/generated/numbering/numbering";
import { ApiError, problemMessage } from "@/lib/problem";
import { useDebounced } from "@/lib/use-debounced";

function SchemeEditor({ scheme }: { scheme: SchemeOut }) {
  const t = useTranslations("numbering");
  const common = useTranslations("common");
  const canEdit = useCan("numbering:manage");
  const queryClient = useQueryClient();
  const [pattern, setPattern] = useState(scheme.pattern);
  const [reset, setReset] = useState(scheme.reset_period);
  const [saving, setSaving] = useState(false);
  const debounced = useDebounced(pattern);

  const preview = useQuery({
    queryKey: ["numbering-preview", debounced],
    queryFn: () => numberingSchemesPreview({ pattern: debounced, branch_code: "HQ" }),
    retry: false,
  });
  const previewError = preview.error instanceof ApiError ? preview.error.problem.errors?.[0]?.message ?? problemMessage(preview.error.problem) : null;
  const dirty = pattern !== scheme.pattern || reset !== scheme.reset_period;

  async function save() {
    setSaving(true);
    try {
      await numberingSchemesUpdate(scheme.id, { pattern, reset_period: reset }, ifMatch(scheme.version));
      await queryClient.invalidateQueries({ queryKey: getNumberingSchemesListQueryKey() });
      toast.success(common("saved"));
    } catch (error) {
      toast.error(error instanceof ApiError ? problemMessage(error.problem) : common("tryAgain"));
    } finally {
      setSaving(false);
    }
  }

  return (
    <li className="grid gap-4 px-4 py-5 sm:grid-cols-[9rem_minmax(0,1fr)]">
      <h3 className="text-lg">{t(scheme.document_type as "quote")}</h3>
      <div className="grid gap-4">
        <div className="grid gap-4 sm:grid-cols-[minmax(0,1fr)_10rem]">
          <Field label={t("pattern")} error={previewError ?? undefined}>
            {(p) => (
              <Input {...p} value={pattern} onChange={(e) => setPattern(e.target.value)} disabled={!canEdit} className="font-heading tracking-wide" spellCheck={false} />
            )}
          </Field>
          <Field label={t("reset")}>
            {(p) => (
              <NativeSelect {...p} value={reset} onChange={(e) => setReset(e.target.value as typeof reset)} disabled={!canEdit}>
                <option value="yearly">{t("yearly")}</option>
                <option value="monthly">{t("monthly")}</option>
                <option value="never">{t("never")}</option>
              </NativeSelect>
            )}
          </Field>
        </div>
        <p className="text-sm text-muted-foreground" aria-live="polite">
          {t("nextNumbers")}:{" "}
          <span className="tabular font-bold text-foreground">{preview.data?.examples.join(", ") ?? "…"}</span>
        </p>
        {canEdit && dirty && (
          <div>
            <Button onClick={save} disabled={saving || !!previewError}>{common("save")}</Button>
          </div>
        )}
      </div>
    </li>
  );
}

export function NumberingPanel() {
  const t = useTranslations("numbering");
  const schemes = useNumberingSchemesList();
  if (!schemes.data) return <Skeleton className="h-80 w-full" />;
  return (
    <>
      <p className="mb-4 max-w-prose text-sm text-muted-foreground">{t("patternHint")}</p>
      <ul className="divide-y rounded-lg border bg-card">
        {schemes.data.filter((s) => !s.branch_id).map((scheme) => (
          <SchemeEditor key={`${scheme.id}-${scheme.version}`} scheme={scheme} />
        ))}
      </ul>
    </>
  );
}
