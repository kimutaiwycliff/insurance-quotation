"use client";

import { useQuery, useQueryClient } from "@tanstack/react-query";
import { Download, ImageUp } from "lucide-react";
import { useTranslations } from "next-intl";
import { useMemo, useRef, useState, type ChangeEvent } from "react";
import { toast } from "sonner";

import { Field } from "@/components/forms/field";
import { useCan } from "@/components/shell/me-context";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Skeleton } from "@/components/ui/skeleton";
import { Textarea } from "@/components/ui/textarea";
import { bffRaw, ifMatch } from "@/lib/api/fetcher";
import {
  brandingUpdate,
  getBrandingGetQueryKey,
  useBrandingGet,
  useTemplatesList,
} from "@/lib/api/generated/branding/branding";
import type { BrandingOut, BrandingUpdate, PaymentDefaults, TemplateOut } from "@/lib/api/generated/model";
import { ApiError, problemMessage } from "@/lib/problem";
import { uploadDocument } from "@/lib/upload";
import { useDebounced } from "@/lib/use-debounced";
import { cn } from "@/lib/utils";

const DOC_TYPES = ["quote", "invoice", "receipt", "credit_note"] as const;
const PREVIEW_TYPES = [
  { value: "quote", label: "documentQuote" },
  { value: "invoice", label: "documentInvoice" },
  { value: "receipt", label: "documentReceipt" },
] as const;
const HEX = /^#[0-9a-fA-F]{6}$/;

interface Draft {
  template: string;
  primary_color: string;
  accent_color: string;
  logo_document_id: string | null;
  footer_text: string;
  payment: PaymentDefaults;
}

/** Empty colour = the template's own colour. */
function draftFrom(b: BrandingOut): Draft {
  return {
    template: b.templates.invoice ?? "classic",
    primary_color: b.primary_color ?? "",
    accent_color: b.accent_color ?? "",
    logo_document_id: b.logo_document_id ?? null,
    footer_text: b.footer_text ?? "",
    payment: b.payment_instructions ?? {},
  };
}

function toUpdate(d: Draft): BrandingUpdate {
  const clean = Object.fromEntries(Object.entries(d.payment).filter(([, v]) => v)) as PaymentDefaults;
  return {
    templates: Object.fromEntries(DOC_TYPES.map((doc) => [doc, d.template])),
    primary_color: HEX.test(d.primary_color) ? d.primary_color.toUpperCase() : undefined,
    accent_color: HEX.test(d.accent_color) ? d.accent_color.toUpperCase() : undefined,
    footer_text: d.footer_text || null,
    payment_instructions: clean,
    ...(d.logo_document_id ? { logo_document_id: d.logo_document_id } : {}),
  };
}

function ColourField({ label, value, onChange, disabled }: { label: string; value: string; onChange: (v: string) => void; disabled?: boolean }) {
  return (
    <Field label={label} error={!value || HEX.test(value) ? undefined : "Use a colour like #0E6B5C"}>
      {(p) => (
        <div className="flex items-center gap-2">
          <span className="relative size-10 shrink-0">
            <input
              type="color"
              aria-label={`${label} picker`}
              value={HEX.test(value) ? value : "#000000"}
              onChange={(e) => onChange(e.target.value)}
              disabled={disabled}
              className="size-10 cursor-pointer rounded-md border bg-card p-1"
            />
            {!value && (
              // Not chosen yet: the design's own colour applies. Show that, not a misleading black swatch.
              <span
                aria-hidden="true"
                className="pointer-events-none absolute inset-1 rounded-sm bg-[repeating-linear-gradient(45deg,var(--muted)_0_4px,var(--card)_4px_8px)]"
              />
            )}
          </span>
          <Input
            {...p}
            value={value}
            placeholder="Design default"
            onChange={(e) => onChange(e.target.value)}
            disabled={disabled}
            className="tabular uppercase placeholder:normal-case"
            maxLength={7}
          />
        </div>
      )}
    </Field>
  );
}

// A4 at 96 dpi. The preview renders at real size and is scaled down, so it is a true miniature.
const A4 = { width: 794, height: 1123 };

function A4Frame({ title, html, dim }: { title: string; html?: string; dim: boolean }) {
  const [scale, setScale] = useState(0.5);
  const observer = useRef<ResizeObserver | null>(null);
  const measure = (node: HTMLDivElement | null) => {
    observer.current?.disconnect();
    if (!node) return;
    observer.current = new ResizeObserver(([entry]) => {
      if (entry) setScale(Math.min(1, entry.contentRect.width / A4.width));
    });
    observer.current.observe(node);
  };
  return (
    <div ref={measure} className="w-full">
      <div
        className="relative overflow-hidden rounded-md border bg-white shadow-sm"
        style={{ height: Math.round(A4.height * scale) }}
      >
        {html ? (
          <iframe
            title={title}
            sandbox=""
            srcDoc={html}
            width={A4.width}
            height={A4.height}
            className={cn("absolute top-0 left-0 origin-top-left border-0 transition-opacity", dim && "opacity-60")}
            style={{ transform: `scale(${scale})` }}
          />
        ) : (
          <Skeleton className="h-full w-full rounded-none" />
        )}
      </div>
    </div>
  );
}

type EditorProps = { onSaved?: () => void; submitLabel?: string };

export function BrandingEditor(props: EditorProps) {
  const branding = useBrandingGet();
  const templates = useTemplatesList();
  if (!branding.data || !templates.data) return <Skeleton className="h-[36rem] w-full" />;
  return <BrandingForm {...props} branding={branding.data} templates={templates.data} />;
}

function BrandingForm({
  onSaved,
  submitLabel,
  branding,
  templates,
}: EditorProps & { branding: BrandingOut; templates: TemplateOut[] }) {
  const t = useTranslations("branding");
  const common = useTranslations("common");
  const canEdit = useCan("branding:manage");
  const queryClient = useQueryClient();
  const [version, setVersion] = useState(branding.version);
  const [draft, setDraft] = useState<Draft>(() => draftFrom(branding));
  const [previewType, setPreviewType] = useState<(typeof PREVIEW_TYPES)[number]["value"]>("quote");
  const [uploading, setUploading] = useState(false);
  const [saving, setSaving] = useState(false);
  const fileInput = useRef<HTMLInputElement>(null);

  const manifest = templates.find((m) => m.key === draft.template);
  const update = useMemo(() => toUpdate(draft), [draft]);
  const debounced = useDebounced(update, 500);
  const preview = useQuery({
    queryKey: ["branding-preview", draft.template, previewType, debounced],
    placeholderData: (previous) => previous,
    queryFn: async () => {
      const response = await bffRaw(`/api/v1/templates/${draft.template}/preview`, {
        method: "POST",
        body: JSON.stringify({ doc_type: previewType, format: "html", branding: debounced }),
      });
      return response.text();
    },
  });

  const set = (patch: Partial<Draft>) => setDraft({ ...draft, ...patch });
  const setPayment = (patch: Partial<PaymentDefaults>) => set({ payment: { ...draft.payment, ...patch } });

  async function onLogo(event: ChangeEvent<HTMLInputElement>) {
    const file = event.target.files?.[0];
    event.target.value = "";
    if (!file) return;
    if (file.size > 1024 * 1024) {
      toast.error("That logo is larger than 1 MB. Use a smaller image.");
      return;
    }
    setUploading(true);
    try {
      const doc = await uploadDocument(file, "branding", "Logo");
      set({ logo_document_id: doc.id });
    } catch (error) {
      toast.error(error instanceof ApiError ? problemMessage(error.problem) : "The logo did not upload. Try again.");
    } finally {
      setUploading(false);
    }
  }

  async function save() {
    setSaving(true);
    try {
      const saved = await brandingUpdate(toUpdate(draft), ifMatch(version));
      queryClient.setQueryData(getBrandingGetQueryKey(), saved);
      setVersion(saved.version);
      toast.success(common("saved"));
      onSaved?.();
    } catch (error) {
      toast.error(error instanceof ApiError ? problemMessage(error.problem) : common("tryAgain"));
    } finally {
      setSaving(false);
    }
  }

  async function downloadPdf() {
    const response = await bffRaw(`/api/v1/templates/${draft.template}/preview`, {
      method: "POST",
      body: JSON.stringify({ doc_type: previewType, format: "pdf", branding: toUpdate(draft) }),
    });
    const url = URL.createObjectURL(await response.blob());
    const link = Object.assign(document.createElement("a"), { href: url, download: `sample-${previewType}.pdf` });
    link.click();
    URL.revokeObjectURL(url);
  }

  return (
    <div className="grid gap-8 xl:grid-cols-[minmax(0,22rem)_minmax(0,1fr)]">
      <fieldset disabled={!canEdit} className="grid content-start gap-7">
        <div role="radiogroup" aria-label={t("template")} className="grid gap-2">
          <span className="text-sm font-bold">{t("template")}</span>
          {templates.map((m) => {
            const selected = draft.template === m.key;
            return (
              <button
                key={m.key}
                type="button"
                role="radio"
                aria-checked={selected}
                onClick={() => set({ template: m.key })}
                className={cn(
                  "grid gap-1 rounded-md border bg-card p-3 text-left transition-colors hover:border-primary",
                  selected && "border-primary ring-2 ring-primary/20",
                )}
              >
                <span className="flex items-center gap-2 font-bold">
                  {m.name}
                  <Badge variant={m.tier === "free" ? "secondary" : "outline"}>{t(m.tier)}</Badge>
                </span>
                <span className="text-sm text-muted-foreground">{m.description}</span>
              </button>
            );
          })}
        </div>

        <div className="grid grid-cols-2 gap-4">
          <ColourField label={t("primary")} value={draft.primary_color} onChange={(v) => set({ primary_color: v })} />
          <ColourField label={t("accent")} value={draft.accent_color} onChange={(v) => set({ accent_color: v })} />
        </div>

        <div className="grid gap-1.5">
          <span className="text-sm font-bold">{t("logo")}</span>
          <input ref={fileInput} type="file" accept="image/png,image/jpeg,image/webp" className="sr-only" onChange={onLogo} aria-label={t("uploadLogo")} />
          <div>
            <Button type="button" variant="outline" onClick={() => fileInput.current?.click()} disabled={uploading}>
              <ImageUp aria-hidden="true" />
              {uploading ? t("uploading") : draft.logo_document_id ? t("replaceLogo") : t("uploadLogo")}
            </Button>
          </div>
          <p className="text-sm text-muted-foreground">{t("logoHint")}</p>
        </div>

        <Field label={t("footer")} hint={t("footerHint")} optional>
          {(p) => <Textarea {...p} rows={2} maxLength={500} value={draft.footer_text} onChange={(e) => set({ footer_text: e.target.value })} />}
        </Field>

        <fieldset className="grid gap-4">
          <legend className="mb-2 text-sm font-bold">{t("payment")}</legend>
          <div className="grid grid-cols-2 gap-4">
            <Field label={t("paybill")} optional>
              {(p) => <Input {...p} inputMode="numeric" value={draft.payment.mpesa_paybill ?? ""} onChange={(e) => setPayment({ mpesa_paybill: e.target.value })} />}
            </Field>
            <Field label={t("till")} optional>
              {(p) => <Input {...p} inputMode="numeric" value={draft.payment.mpesa_till ?? ""} onChange={(e) => setPayment({ mpesa_till: e.target.value })} />}
            </Field>
          </div>
          <Field label={t("bankName")} optional>
            {(p) => <Input {...p} value={draft.payment.bank_name ?? ""} onChange={(e) => setPayment({ bank_name: e.target.value })} />}
          </Field>
          <div className="grid grid-cols-2 gap-4">
            <Field label={t("bankAccountName")} optional>
              {(p) => <Input {...p} value={draft.payment.bank_account_name ?? ""} onChange={(e) => setPayment({ bank_account_name: e.target.value })} />}
            </Field>
            <Field label={t("bankAccountNumber")} optional>
              {(p) => <Input {...p} inputMode="numeric" value={draft.payment.bank_account_number ?? ""} onChange={(e) => setPayment({ bank_account_number: e.target.value })} />}
            </Field>
          </div>
        </fieldset>

        {canEdit && (
          <div>
            <Button size="lg" onClick={save} disabled={saving || uploading}>{submitLabel ?? common("save")}</Button>
          </div>
        )}
      </fieldset>

      <section aria-label={t("preview")} className="grid content-start gap-3 xl:sticky xl:top-20">
        <div className="flex flex-wrap items-center gap-2">
          <div role="tablist" aria-label={t("preview")} className="flex rounded-md border bg-card p-0.5">
            {PREVIEW_TYPES.map(({ value, label }) => (
              <button
                key={value}
                role="tab"
                type="button"
                aria-selected={previewType === value}
                onClick={() => setPreviewType(value)}
                className={cn("rounded px-3 py-1.5 text-sm", previewType === value && "bg-primary text-primary-foreground")}
              >
                {t(label)}
              </button>
            ))}
          </div>
          <Button type="button" variant="ghost" size="sm" onClick={downloadPdf} className="ml-auto">
            <Download aria-hidden="true" /> {t("downloadPdf")}
          </Button>
        </div>
        <A4Frame
          title={t("previewOf", { document: t(PREVIEW_TYPES.find((p) => p.value === previewType)!.label) })}
          html={preview.data}
          dim={preview.isFetching}
        />
        {manifest && <p className="text-sm text-muted-foreground">{manifest.name}: {manifest.description}</p>}
      </section>
    </div>
  );
}
