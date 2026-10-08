"use client";

import { zodResolver } from "@hookform/resolvers/zod";
import { useQuery } from "@tanstack/react-query";
import Link from "next/link";
import { useTranslations } from "next-intl";
import { useForm, useWatch } from "react-hook-form";
import { z } from "zod";

import { Field, FormError } from "@/components/forms/field";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { NativeSelect } from "@/components/ui/native-select";
import { Textarea } from "@/components/ui/textarea";
import { clientsCheckDuplicates } from "@/lib/api/generated/clients/clients";
import type { ClientCreate, ClientOut, ClientUpdate } from "@/lib/api/generated/model";
import { applyApiError } from "@/lib/forms";
import { ApiError } from "@/lib/problem";
import { useDebounced } from "@/lib/use-debounced";
import { cn } from "@/lib/utils";

const text = z.string().trim().max(200).optional().or(z.literal(""));
export const clientSchema = z
  .object({
    kind: z.enum(["individual", "corporate"]),
    first_name: text,
    last_name: text,
    company_name: text,
    phone: z.string().trim().max(30).optional().or(z.literal("")),
    email: z.email("Enter a valid email address").optional().or(z.literal("")),
    preferred_channel: z.enum(["whatsapp", "sms", "email", "call"]),
    kra_pin: z.string().trim().regex(/^([AaPp]\d{9}[A-Za-z])?$/, "A KRA PIN looks like A012345678Z").optional(),
    id_number: z.string().trim().max(30).optional(),
    date_of_birth: z.string().optional(),
    occupation: text,
    town: text,
    tags: z.string().max(300).optional(),
    notes: z.string().max(5000).optional(),
    marketing_consent: z.boolean(),
    allow_duplicate: z.boolean(),
  })
  .superRefine((v, ctx) => {
    if (v.kind === "individual" && !v.first_name) ctx.addIssue({ code: "custom", path: ["first_name"], message: "Enter a first name" });
    if (v.kind === "individual" && !v.last_name) ctx.addIssue({ code: "custom", path: ["last_name"], message: "Enter a last name" });
    if (v.kind === "corporate" && !v.company_name) ctx.addIssue({ code: "custom", path: ["company_name"], message: "Enter the company name" });
  });
export type ClientValues = z.input<typeof clientSchema>;
const FIELDS = ["first_name", "last_name", "company_name", "phone", "email", "kra_pin", "id_number", "date_of_birth", "tags"];

const blank = (v?: string | null) => (v ? v : undefined);

export function toPayload(values: ClientValues): ClientCreate {
  const v = clientSchema.parse(values);
  return {
    kind: v.kind,
    first_name: v.kind === "individual" ? blank(v.first_name) : undefined,
    last_name: v.kind === "individual" ? blank(v.last_name) : undefined,
    company_name: v.kind === "corporate" ? blank(v.company_name) : undefined,
    phone: blank(v.phone),
    email: blank(v.email),
    preferred_channel: v.preferred_channel,
    kra_pin: blank(v.kra_pin),
    id_number: blank(v.id_number),
    date_of_birth: blank(v.date_of_birth),
    occupation: blank(v.occupation),
    address: v.town ? { town: v.town } : undefined,
    tags: v.tags ? v.tags.split(",").map((t) => t.trim()).filter(Boolean) : undefined,
    notes: blank(v.notes),
    marketing_consent: v.marketing_consent,
    allow_duplicate: v.allow_duplicate,
  };
}

export function fromClient(c: ClientOut): ClientValues {
  return {
    kind: c.kind as "individual" | "corporate",
    first_name: c.first_name ?? "",
    last_name: c.last_name ?? "",
    company_name: c.company_name ?? "",
    phone: c.phone ?? "",
    email: c.email ?? "",
    preferred_channel: c.preferred_channel as ClientValues["preferred_channel"],
    kra_pin: c.kra_pin ?? "",
    id_number: "",
    date_of_birth: c.date_of_birth ?? "",
    occupation: c.occupation ?? "",
    town: (c.address as { town?: string }).town ?? "",
    tags: c.tags.join(", "),
    notes: c.notes ?? "",
    marketing_consent: c.marketing_consent,
    allow_duplicate: false,
  };
}

/** Only fields that changed (empty strings clear them). The ID number is sent only when retyped. */
export function toUpdate(values: ClientValues, dirty: Partial<Record<keyof ClientValues, unknown>>): ClientUpdate {
  const full = toPayload(values) as Record<string, unknown>;
  const out: Record<string, unknown> = {};
  const map: Record<string, string> = { town: "address" };
  for (const key of Object.keys(dirty) as (keyof ClientValues)[]) {
    if (key === "kind" || key === "allow_duplicate") continue;
    const target = map[key] ?? key;
    out[target] = full[target] ?? (target === "tags" ? [] : target === "address" ? {} : null);
  }
  if (!values.id_number) delete out.id_number;
  return out as ClientUpdate;
}

function DuplicateWarning({ values, excludeId }: { values: ClientValues; excludeId?: string }) {
  const t = useTranslations("clients");
  const check = useDebounced({ phone: values.phone, email: values.email, kra_pin: values.kra_pin, id_number: values.id_number }, 600);
  const enabled = Boolean(check.phone && check.phone.replace(/\D/g, "").length >= 9) || Boolean(check.email?.includes("@") && check.email.includes(".")) || Boolean(check.kra_pin?.length === 11) || Boolean(check.id_number && check.id_number.length >= 6);
  const result = useQuery({
    queryKey: ["client-duplicates", check, excludeId],
    enabled,
    retry: false,
    queryFn: () =>
      clientsCheckDuplicates({
        phone: check.phone || undefined,
        email: check.email?.includes("@") ? check.email : undefined,
        kra_pin: check.kra_pin?.length === 11 ? check.kra_pin : undefined,
        id_number: check.id_number || undefined,
        exclude_id: excludeId,
      }).catch((error: unknown) => {
        if (error instanceof ApiError && error.status === 422) return { matches: [], hidden: 0 };
        throw error;
      }),
  });
  const data = enabled ? result.data : undefined;
  if (!data || (data.matches.length === 0 && data.hidden === 0)) return null;
  return (
    <div role="status" className="grid gap-2 rounded-md border border-maize bg-maize/10 p-3 text-sm sm:col-span-2">
      <p className="font-bold">{t("duplicateTitle")}</p>
      <ul className="grid gap-1">
        {data.matches.map((m) => (
          <li key={m.client.id}>
            <Link href={`/clients/${m.client.id}`} className="font-bold text-primary underline-offset-4 hover:underline" target="_blank">
              {m.client.display_name}
            </Link>{" "}
            <span className="text-muted-foreground">({m.matched_on.join(", ").replace("_", " ")})</span>
          </li>
        ))}
      </ul>
      {data.hidden > 0 && <p>{t("duplicateHidden", { count: data.hidden })}</p>}
    </div>
  );
}

export function ClientForm({
  initial,
  clientId,
  onSubmit,
  submitLabel,
}: {
  initial?: ClientValues;
  clientId?: string;
  onSubmit: (values: ClientValues, dirty: Partial<Record<keyof ClientValues, unknown>>) => Promise<void>;
  submitLabel: string;
}) {
  const t = useTranslations("clients");
  const form = useForm<ClientValues>({
    resolver: zodResolver(clientSchema),
    defaultValues: initial ?? {
      kind: "individual",
      preferred_channel: "whatsapp",
      marketing_consent: false,
      allow_duplicate: false,
    },
  });
  const values = useWatch({ control: form.control }) as ClientValues;
  const { errors, isSubmitting, dirtyFields } = form.formState;
  const reg = form.register;
  const corporate = values.kind === "corporate";

  async function submit(v: ClientValues) {
    try {
      await onSubmit(v, dirtyFields as Partial<Record<keyof ClientValues, unknown>>);
    } catch (error) {
      if (error instanceof ApiError && error.code === "possible_duplicate") {
        form.setError("root", { message: error.problem.detail ?? t("duplicateTitle") });
        return;
      }
      applyApiError(error, form.setError, FIELDS);
    }
  }

  return (
    <form onSubmit={form.handleSubmit(submit)} noValidate className="grid gap-5 sm:grid-cols-2">
      {!clientId && (
        <div role="radiogroup" aria-label="Client type" className="flex rounded-md border bg-card p-0.5 sm:col-span-2">
          {(["individual", "corporate"] as const).map((kind) => (
            <button
              key={kind}
              type="button"
              role="radio"
              aria-checked={values.kind === kind}
              onClick={() => form.setValue("kind", kind, { shouldDirty: true })}
              className={cn("flex-1 rounded px-3 py-2 text-sm font-bold", values.kind === kind && "bg-primary text-primary-foreground")}
            >
              {t(kind)}
            </button>
          ))}
        </div>
      )}
      <FormError message={errors.root?.message} />
      {corporate ? (
        <Field label={t("companyName")} error={errors.company_name?.message} className="sm:col-span-2">
          {(p) => <Input {...p} autoComplete="organization" {...reg("company_name")} />}
        </Field>
      ) : (
        <>
          <Field label={t("firstName")} error={errors.first_name?.message}>
            {(p) => <Input {...p} autoComplete="given-name" {...reg("first_name")} />}
          </Field>
          <Field label={t("lastName")} error={errors.last_name?.message}>
            {(p) => <Input {...p} autoComplete="family-name" {...reg("last_name")} />}
          </Field>
        </>
      )}
      <Field label={t("phone")} error={errors.phone?.message}>
        {(p) => <Input {...p} type="tel" inputMode="tel" placeholder="0712 345 678" {...reg("phone")} />}
      </Field>
      <Field label={t("email")} optional error={errors.email?.message}>
        {(p) => <Input {...p} type="email" inputMode="email" {...reg("email")} />}
      </Field>
      <Field label={t("kraPin")} optional error={errors.kra_pin?.message}>
        {(p) => <Input {...p} className="uppercase" autoCapitalize="characters" {...reg("kra_pin")} />}
      </Field>
      <Field label={t("idNumber")} optional hint={t("idHint")} error={errors.id_number?.message}>
        {(p) => <Input {...p} autoComplete="off" {...reg("id_number")} />}
      </Field>
      <DuplicateWarning values={values} excludeId={clientId} />
      <Field label={t("preferredChannel")}>
        {(p) => (
          <NativeSelect {...p} {...reg("preferred_channel")}>
            <option value="whatsapp">{t("whatsapp")}</option>
            <option value="call">{t("call")}</option>
            <option value="sms">{t("sms")}</option>
            <option value="email">{t("email")}</option>
          </NativeSelect>
        )}
      </Field>
      {!corporate && (
        <Field label={t("dob")} optional error={errors.date_of_birth?.message}>
          {(p) => <Input {...p} type="date" {...reg("date_of_birth")} />}
        </Field>
      )}
      <Field label={t("town")} optional>
        {(p) => <Input {...p} autoComplete="address-level2" {...reg("town")} />}
      </Field>
      <Field label={t("occupation")} optional>
        {(p) => <Input {...p} {...reg("occupation")} />}
      </Field>
      <Field label={t("tags")} optional hint={t("tagsHint")} error={errors.tags?.message} className="sm:col-span-2">
        {(p) => <Input {...p} {...reg("tags")} />}
      </Field>
      <Field label={t("notes")} optional className="sm:col-span-2">
        {(p) => <Textarea {...p} rows={3} {...reg("notes")} />}
      </Field>
      <label className="flex items-start gap-2 text-sm sm:col-span-2">
        <input type="checkbox" className="mt-1 size-4 accent-[var(--acacia)]" {...reg("marketing_consent")} />
        {t("consent")}
      </label>
      {errors.root && (
        <label className="flex items-start gap-2 text-sm font-bold sm:col-span-2">
          <input type="checkbox" className="mt-1 size-4 accent-[var(--acacia)]" {...reg("allow_duplicate")} />
          {t("createAnyway")}
        </label>
      )}
      <div className="sm:col-span-2">
        <Button type="submit" size="lg" disabled={isSubmitting}>{submitLabel}</Button>
      </div>
    </form>
  );
}
