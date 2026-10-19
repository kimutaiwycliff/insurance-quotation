"use client";

import { useQueries, useQuery, useQueryClient } from "@tanstack/react-query";
import { Check, Download, ImageUp, Trash2 } from "lucide-react";
import { useTranslations } from "next-intl";
import { useId, useMemo, useRef, useState, type ChangeEvent, type ReactNode } from "react";
import { toast } from "sonner";

import { Field } from "@/components/forms/field";
import { useCan } from "@/components/shell/me-context";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Skeleton } from "@/components/ui/skeleton";
import { Switch } from "@/components/ui/switch";
import { Textarea } from "@/components/ui/textarea";
import { bffRaw, ifMatch } from "@/lib/api/fetcher";
import {
  brandingUpdate,
  getBrandingGetQueryKey,
  useBrandingGet,
  useTemplatesList,
} from "@/lib/api/generated/branding/branding";
import type {
  BrandingOut,
  BrandingUpdate,
  BrandingUpdateFontPair,
  DesignOptionsUpdate,
  PaymentDefaults,
  TemplateOut,
} from "@/lib/api/generated/model";
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

/** Ready-made colour pairs (main, highlight). Empty = the design's own colours. */
const PRESETS = [
  { name: "Acacia", primary: "#0E6B5C", accent: "#F2B705" },
  { name: "Ocean", primary: "#1C6E8C", accent: "#F4A261" },
  { name: "Indigo and saffron", primary: "#233D7A", accent: "#E0A526" },
  { name: "Wine and gold", primary: "#6B1D2A", accent: "#B8892B" },
  { name: "Forest", primary: "#1E3A34", accent: "#B7791F" },
  { name: "Charcoal", primary: "#1F2937", accent: "#9CA3AF" },
  { name: "Royal", primary: "#3730A3", accent: "#F59E0B" },
  { name: "Clay", primary: "#7C2D12", accent: "#0F766E" },
];

const FONTS: { value: BrandingUpdateFontPair; name: string; hint: string }[] = [
  { value: "sans", name: "Modern sans", hint: "Clean and easy to read" },
  { value: "serif", name: "Refined serif", hint: "Serif headings, sans text" },
  { value: "geometric", name: "Geometric", hint: "Confident, rounded headings" },
  { value: "editorial", name: "Editorial", hint: "Characterful display serif" },
  { value: "classic", name: "Classic book", hint: "Serif throughout, traditional" },
  { value: "ledger", name: "Ledger", hint: "Typewriter figures, accounts feel" },
];

type Align = NonNullable<DesignOptionsUpdate["logo_align"]>;
type Size = NonNullable<DesignOptionsUpdate["logo_size"]>;
type Paper = NonNullable<DesignOptionsUpdate["paper"]>;

interface Draft {
  template: string;
  primary_color: string;
  accent_color: string;
  font_pair: BrandingUpdateFontPair | "";
  logo_document_id: string | null;
  footer_text: string;
  payment: PaymentDefaults;
  logo_size: Size;
  logo_align: Align | null;
  show_payment: boolean;
  show_signature: boolean;
  seal_watermark: boolean;
  paper: Paper | null;
}

/** Empty colour or font = the design's own. */
function draftFrom(b: BrandingOut): Draft {
  const o = b.options ?? {};
  return {
    template: b.templates.invoice ?? "classic",
    primary_color: b.primary_color ?? "",
    accent_color: b.accent_color ?? "",
    font_pair: (b.font_pair as BrandingUpdateFontPair | null) ?? "",
    logo_document_id: b.logo_document_id ?? null,
    footer_text: b.footer_text ?? "",
    payment: b.payment_instructions ?? {},
    logo_size: o.logo_size ?? "medium",
    logo_align: o.logo_align ?? null,
    show_payment: o.show_payment ?? true,
    show_signature: o.show_signature ?? false,
    seal_watermark: o.seal_watermark ?? false,
    paper: o.paper ?? null,
  };
}

function toUpdate(d: Draft): BrandingUpdate {
  const clean = Object.fromEntries(Object.entries(d.payment).filter(([, v]) => v)) as PaymentDefaults;
  return {
    templates: Object.fromEntries(DOC_TYPES.map((doc) => [doc, d.template])),
    primary_color: HEX.test(d.primary_color) ? d.primary_color.toUpperCase() : null,
    accent_color: HEX.test(d.accent_color) ? d.accent_color.toUpperCase() : null,
    font_pair: d.font_pair || null,
    footer_text: d.footer_text || null,
    payment_instructions: clean,
    logo_document_id: d.logo_document_id, // null removes the logo
    options: {
      logo_size: d.logo_size,
      logo_align: d.logo_align, // null: the design's own
      show_payment: d.show_payment,
      show_signature: d.show_signature,
      seal_watermark: d.seal_watermark,
      paper: d.paper,
    },
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

/** A row of mutually exclusive choices. */
function Segmented<T extends string>({ label, value, options, onChange }: { label: string; value: T; options: { value: T; label: string }[]; onChange: (v: T) => void }) {
  return (
    <div className="grid gap-1.5">
      <span className="text-sm font-bold">{label}</span>
      <div role="radiogroup" aria-label={label} className="flex flex-wrap rounded-md border bg-card p-0.5">
        {options.map((o) => (
          <button
            key={o.value}
            type="button"
            role="radio"
            aria-checked={value === o.value}
            onClick={() => onChange(o.value)}
            className={cn("flex-1 rounded px-2.5 py-1.5 text-sm whitespace-nowrap", value === o.value ? "bg-primary font-bold text-primary-foreground" : "hover:bg-accent")}
          >
            {o.label}
          </button>
        ))}
      </div>
    </div>
  );
}

function Toggle({ label, hint, checked, onChange }: { label: string; hint: string; checked: boolean; onChange: (v: boolean) => void }) {
  const id = useId();
  return (
    <div className="flex items-start justify-between gap-4">
      <label htmlFor={id} className="grid gap-0.5">
        <span className="font-bold">{label}</span>
        <span className="text-sm text-muted-foreground">{hint}</span>
      </label>
      <Switch id={id} checked={checked} onCheckedChange={onChange} className="mt-1" />
    </div>
  );
}

function Group({ title, children }: { title: string; children: ReactNode }) {
  return (
    <fieldset className="grid gap-4">
      <legend className="mb-3 font-heading text-lg">{title}</legend>
      {children}
    </fieldset>
  );
}

// A4 at 96 dpi. The preview renders at real size and is scaled down, so it is a true miniature.
const A4 = { width: 794, height: 1123 };

function A4Frame({ title, html, dim, decorative = false }: { title: string; html?: string; dim: boolean; decorative?: boolean }) {
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
    <div ref={measure} className="w-full" aria-hidden={decorative || undefined}>
      <div className="relative overflow-hidden rounded-md border bg-white shadow-sm" style={{ height: Math.round(A4.height * scale) }}>
        {html ? (
          <iframe
            title={title}
            sandbox=""
            srcDoc={html}
            width={A4.width}
            height={A4.height}
            tabIndex={decorative ? -1 : undefined}
            loading={decorative ? "lazy" : undefined}
            className={cn("pointer-events-none absolute top-0 left-0 origin-top-left border-0 transition-opacity", dim && "opacity-60")}
            style={{ transform: `scale(${scale})` }}
          />
        ) : (
          <Skeleton className="h-full w-full rounded-none" />
        )}
      </div>
    </div>
  );
}

async function previewHtml(template: string, docType: string, branding: BrandingUpdate): Promise<string> {
  const response = await bffRaw(`/api/v1/templates/${template}/preview`, {
    method: "POST",
    body: JSON.stringify({ doc_type: docType, format: "html", branding }),
  });
  return response.text();
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
    queryFn: () => previewHtml(draft.template, previewType, debounced),
  });
  // Gallery thumbnails: every design with the agency's own colours, logo and options (the design's own
  // colours when none are chosen). They follow the choices below, a little more lazily than the big preview.
  const gallery = useDebounced({ ...debounced, templates: undefined }, 900);
  const thumbnails = useQueries({
    queries: templates.map((m) => ({
      queryKey: ["branding-thumb", m.key, gallery],
      placeholderData: (previous: string | undefined) => previous,
      staleTime: 60_000,
      queryFn: () => previewHtml(m.key, "invoice", gallery),
    })),
  });

  const set = (patch: Partial<Draft>) => setDraft((d) => ({ ...d, ...patch }));
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

  const presetActive = (p: (typeof PRESETS)[number]) => draft.primary_color.toUpperCase() === p.primary && draft.accent_color.toUpperCase() === p.accent;

  return (
    <div className="grid gap-10">
      <section className="grid gap-3">
        <div className="flex flex-wrap items-end justify-between gap-2">
          <div>
            <h2 className="text-xl">{t("template")}</h2>
            <p className="text-sm text-muted-foreground">{templates.length} designs, shown with your colours and logo. Pick one, then make it yours below.</p>
          </div>
        </div>
        <div role="radiogroup" aria-label={t("template")} className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-4 2xl:grid-cols-6">
          {templates.map((m, i) => {
            const selected = draft.template === m.key;
            return (
              <div key={m.key} className={cn("group relative grid gap-2 rounded-lg border bg-card p-2 transition-colors", selected ? "border-primary ring-2 ring-primary/30" : "hover:border-primary")}>
                <A4Frame title={`${m.name} design`} html={thumbnails[i]?.data} dim={Boolean(thumbnails[i]?.isFetching)} decorative />
                <button
                  type="button"
                  role="radio"
                  aria-checked={selected}
                  disabled={!canEdit}
                  onClick={() => set({ template: m.key })}
                  className="grid gap-0.5 text-left after:absolute after:inset-0 after:rounded-lg after:content-[''] focus-visible:outline-none focus-visible:after:outline-3 focus-visible:after:outline-maize"
                >
                  <span className="flex items-center gap-1.5 font-bold">
                    {selected && <Check aria-hidden="true" className="size-4 text-primary" />}
                    {m.name}
                    <Badge variant={m.tier === "free" ? "secondary" : "outline"} className="ml-auto">{t(m.tier)}</Badge>
                  </span>
                  <span className="line-clamp-2 text-xs text-muted-foreground">{m.description}</span>
                </button>
              </div>
            );
          })}
        </div>
      </section>

      <div className="grid gap-8 xl:grid-cols-[minmax(0,24rem)_minmax(0,1fr)]">
        <fieldset disabled={!canEdit} className="grid content-start gap-9">
          <Group title="Colours">
            <div role="radiogroup" aria-label="Colour presets" className="flex flex-wrap gap-2">
              <button
                type="button"
                role="radio"
                aria-checked={!draft.primary_color && !draft.accent_color}
                onClick={() => set({ primary_color: "", accent_color: "" })}
                className={cn("rounded-full border px-3 py-1 text-sm", !draft.primary_color && !draft.accent_color ? "border-primary bg-primary/10 font-bold" : "hover:border-primary")}
              >
                Design colours
              </button>
              {PRESETS.map((p) => (
                <button
                  key={p.name}
                  type="button"
                  role="radio"
                  aria-checked={presetActive(p)}
                  aria-label={p.name}
                  title={p.name}
                  onClick={() => set({ primary_color: p.primary, accent_color: p.accent })}
                  className={cn("flex size-9 overflow-hidden rounded-full border-2", presetActive(p) ? "border-foreground" : "border-transparent hover:border-input")}
                >
                  <span className="h-full w-2/3" style={{ background: p.primary }} />
                  <span className="h-full w-1/3" style={{ background: p.accent }} />
                </button>
              ))}
            </div>
            <div className="grid grid-cols-2 gap-4">
              <ColourField label={t("primary")} value={draft.primary_color} onChange={(v) => set({ primary_color: v })} />
              <ColourField label={t("accent")} value={draft.accent_color} onChange={(v) => set({ accent_color: v })} />
            </div>
          </Group>

          <Group title="Fonts">
            <div role="radiogroup" aria-label="Fonts" className="grid grid-cols-2 gap-2">
              {[{ value: "" as const, name: "Design default", hint: `As ${manifest?.name ?? "the design"} intends` }, ...FONTS].map((f) => {
                const selected = draft.font_pair === f.value;
                return (
                  <button
                    key={f.value || "default"}
                    type="button"
                    role="radio"
                    aria-checked={selected}
                    onClick={() => set({ font_pair: f.value })}
                    className={cn("grid gap-0.5 rounded-md border bg-card px-3 py-2 text-left", selected ? "border-primary ring-2 ring-primary/20" : "hover:border-primary")}
                  >
                    <span className="font-bold">{f.name}</span>
                    <span className="text-xs text-muted-foreground">{f.hint}</span>
                  </button>
                );
              })}
            </div>
          </Group>

          <Group title={t("logo")}>
            <input ref={fileInput} type="file" accept="image/png,image/jpeg,image/webp" className="sr-only" onChange={onLogo} aria-label={t("uploadLogo")} />
            <div className="flex flex-wrap gap-2">
              <Button type="button" variant="outline" onClick={() => fileInput.current?.click()} disabled={uploading}>
                <ImageUp aria-hidden="true" />
                {uploading ? t("uploading") : draft.logo_document_id ? t("replaceLogo") : t("uploadLogo")}
              </Button>
              {draft.logo_document_id && (
                <Button type="button" variant="ghost" className="text-destructive" onClick={() => set({ logo_document_id: null })}>
                  <Trash2 aria-hidden="true" /> Remove logo
                </Button>
              )}
            </div>
            <p className="-mt-2 text-sm text-muted-foreground">
              {draft.logo_document_id ? t("logoHint") : "No logo: your agency name is shown instead. " + t("logoHint")}
            </p>
            <Segmented<Size>
              label="Logo size"
              value={draft.logo_size}
              onChange={(v) => set({ logo_size: v })}
              options={[{ value: "small", label: "Small" }, { value: "medium", label: "Medium" }, { value: "large", label: "Large" }]}
            />
            <Segmented<Align | "auto">
              label="Logo position"
              value={draft.logo_align ?? "auto"}
              onChange={(v) => set({ logo_align: v === "auto" ? null : v })}
              options={[{ value: "auto", label: "Design's own" }, { value: "start", label: "Left" }, { value: "center", label: "Centre" }, { value: "end", label: "Right" }]}
            />
          </Group>

          <Group title="On the page">
            <Toggle label="How to pay box" hint="Your M-Pesa and bank details on invoices." checked={draft.show_payment} onChange={(v) => set({ show_payment: v })} />
            <Toggle label="Signature and stamp lines" hint="Space to sign and stamp printed copies. Always on in Corporate." checked={draft.show_signature} onChange={(v) => set({ show_signature: v })} />
            <Toggle label="Agency seal watermark" hint="Your round agency seal, very faint, behind the page." checked={draft.seal_watermark} onChange={(v) => set({ seal_watermark: v })} />
            <Segmented<Paper | "auto">
              label="Paper"
              value={draft.paper ?? "auto"}
              onChange={(v) => set({ paper: v === "auto" ? null : v })}
              options={[{ value: "auto", label: "Design's own (A4)" }, { value: "A4", label: "A4" }, { value: "Letter", label: "Letter" }]}
            />
          </Group>

          <Field label={t("footer")} hint={t("footerHint")} optional>
            {(p) => <Textarea {...p} rows={2} maxLength={500} value={draft.footer_text} onChange={(e) => set({ footer_text: e.target.value })} />}
          </Field>

          <fieldset className="grid gap-4">
            <legend className="mb-2 font-heading text-lg">{t("payment")}</legend>
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
    </div>
  );
}
