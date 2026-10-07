"use client";

import { zodResolver } from "@hookform/resolvers/zod";
import { useQueryClient } from "@tanstack/react-query";
import { useRouter } from "next/navigation";
import { useTranslations } from "next-intl";
import { useEffect } from "react";
import { useForm } from "react-hook-form";
import { toast } from "sonner";
import { z } from "zod";

import { Field } from "@/components/forms/field";
import { useCan } from "@/components/shell/me-context";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { NativeSelect } from "@/components/ui/native-select";
import { Skeleton } from "@/components/ui/skeleton";
import { ifMatch } from "@/lib/api/fetcher";
import type { OrganizationOut, OrganizationUpdate } from "@/lib/api/generated/model";
import {
  getOrganizationGetQueryKey,
  organizationUpdate,
  useOrganizationGet,
} from "@/lib/api/generated/organization/organization";
import { applyApiError } from "@/lib/forms";

const optional = z.string().trim().max(200).optional().or(z.literal(""));
export const organizationSchema = z.object({
  name: z.string().trim().min(2, "Enter the name clients know you by").max(200),
  legal_name: optional,
  registration_number: optional,
  tax_pin: z
    .string()
    .trim()
    .toUpperCase()
    .regex(/^([AP]\d{9}[A-Z])?$/, "A KRA PIN looks like P051234567X")
    .optional(),
  licence_number: optional,
  licence_expiry: z.string().optional(),
  intermediary_type: z.enum(["agent", "broker", "business"]),
  email: z.email("Enter a valid email address").optional().or(z.literal("")),
  phone: z
    .string()
    .trim()
    .regex(/^(\+?[0-9 ]{7,20})?$/, "Use digits, e.g. +254 712 345 678")
    .optional(),
  default_currency: z.string().length(3),
  timezone: z.string(),
  fiscal_year_start_month: z.coerce.number().int().min(1).max(12),
  quiet_hours_start: z.string().optional(),
  quiet_hours_end: z.string().optional(),
});
export type OrganizationValues = z.input<typeof organizationSchema>;

export const TIMEZONES = ["Africa/Nairobi", "Africa/Kampala", "Africa/Dar_es_Salaam", "Africa/Kigali", "Africa/Addis_Ababa", "Africa/Lagos", "Africa/Johannesburg", "Europe/London", "UTC"];
export const CURRENCIES = ["KES", "UGX", "TZS", "RWF", "USD", "EUR", "GBP"];
const MONTHS = Array.from({ length: 12 }, (_, i) => new Intl.DateTimeFormat("en-KE", { month: "long" }).format(new Date(2026, i, 1)));
const FIELDS = Object.keys(organizationSchema.shape);

function toValues(org: OrganizationOut): OrganizationValues {
  return {
    name: org.name,
    legal_name: org.legal_name ?? "",
    registration_number: org.registration_number ?? "",
    tax_pin: org.tax_pin ?? "",
    licence_number: org.licence_number ?? "",
    licence_expiry: org.licence_expiry ?? "",
    intermediary_type: org.intermediary_type as OrganizationValues["intermediary_type"],
    email: org.email ?? "",
    phone: org.phone ?? "",
    default_currency: org.default_currency,
    timezone: org.timezone,
    fiscal_year_start_month: org.fiscal_year_start_month,
    quiet_hours_start: org.quiet_hours_start?.slice(0, 5) ?? "",
    quiet_hours_end: org.quiet_hours_end?.slice(0, 5) ?? "",
  };
}

/** Only changed fields are sent; empty strings clear optional fields. */
export function changedFields(values: OrganizationValues, dirty: Partial<Record<string, unknown>>): OrganizationUpdate {
  const parsed = organizationSchema.parse(values);
  const out: Record<string, unknown> = {};
  for (const [key, value] of Object.entries(parsed)) {
    if (!dirty[key]) continue;
    out[key] = value === "" ? null : value;
  }
  return out as OrganizationUpdate;
}

export function OrganizationForm({ compact = false, onSaved }: { compact?: boolean; onSaved?: () => void }) {
  const t = useTranslations("organization");
  const common = useTranslations("common");
  const canEdit = useCan("org:update");
  const queryClient = useQueryClient();
  const router = useRouter();
  const query = useOrganizationGet();
  const form = useForm<OrganizationValues>({ resolver: zodResolver(organizationSchema) });
  const { errors, dirtyFields, isSubmitting, isDirty } = form.formState;

  useEffect(() => {
    if (query.data) form.reset(toValues(query.data));
  }, [query.data, form]);

  if (!query.data) return <Skeleton className="h-96 w-full" />;
  const org = query.data;

  async function onSubmit(values: OrganizationValues) {
    try {
      const saved = await organizationUpdate(changedFields(values, dirtyFields), ifMatch(org.version));
      queryClient.setQueryData(getOrganizationGetQueryKey(), saved);
      form.reset(toValues(saved));
      toast.success(common("saved"));
      router.refresh(); // agency name in the shell
      onSaved?.();
    } catch (error) {
      applyApiError(error, form.setError, FIELDS);
    }
  }

  const reg = form.register;
  return (
    <form onSubmit={form.handleSubmit(onSubmit)} noValidate className="grid gap-6">
      <fieldset disabled={!canEdit} className="grid gap-5 sm:grid-cols-2">
        <Field label={t("name")} error={errors.name?.message} className="sm:col-span-2">
          {(p) => <Input {...p} {...reg("name")} autoComplete="organization" />}
        </Field>
        <Field label={t("intermediaryType")} className="sm:col-span-2">
          {(p) => (
            <NativeSelect {...p} {...reg("intermediary_type")}>
              <option value="agent">{t("agent")}</option>
              <option value="broker">{t("broker")}</option>
              <option value="business">{t("business")}</option>
            </NativeSelect>
          )}
        </Field>
        <Field label={t("taxPin")} optional error={errors.tax_pin?.message}>
          {(p) => <Input {...p} {...reg("tax_pin")} className="uppercase" autoCapitalize="characters" />}
        </Field>
        <Field label={t("licenceNumber")} optional error={errors.licence_number?.message}>
          {(p) => <Input {...p} {...reg("licence_number")} />}
        </Field>
        <Field label={t("email")} optional error={errors.email?.message}>
          {(p) => <Input {...p} type="email" inputMode="email" {...reg("email")} />}
        </Field>
        <Field label={t("phone")} optional error={errors.phone?.message}>
          {(p) => <Input {...p} type="tel" inputMode="tel" {...reg("phone")} />}
        </Field>
        {!compact && (
          <>
            <Field label={t("legalName")} optional error={errors.legal_name?.message}>
              {(p) => <Input {...p} {...reg("legal_name")} />}
            </Field>
            <Field label={t("registrationNumber")} optional>
              {(p) => <Input {...p} {...reg("registration_number")} />}
            </Field>
            <Field label={t("licenceExpiry")} optional>
              {(p) => <Input {...p} type="date" {...reg("licence_expiry")} />}
            </Field>
            <Field label={t("currency")}>
              {(p) => (
                <NativeSelect {...p} {...reg("default_currency")}>
                  {CURRENCIES.map((c) => <option key={c}>{c}</option>)}
                </NativeSelect>
              )}
            </Field>
            <Field label={t("timezone")}>
              {(p) => (
                <NativeSelect {...p} {...reg("timezone")}>
                  {TIMEZONES.map((z) => <option key={z} value={z}>{z.replace("_", " ").replace("/", " / ")}</option>)}
                </NativeSelect>
              )}
            </Field>
            <Field label={t("fiscalYear")}>
              {(p) => (
                <NativeSelect {...p} {...reg("fiscal_year_start_month")}>
                  {MONTHS.map((m, i) => <option key={m} value={i + 1}>{m}</option>)}
                </NativeSelect>
              )}
            </Field>
            <div className="grid gap-1.5 sm:col-span-2">
              <span className="text-sm font-bold">{t("quietHours")}</span>
              <div className="flex items-center gap-2">
                <Input type="time" aria-label="From" className="w-36" {...reg("quiet_hours_start")} />
                <span>{t("and")}</span>
                <Input type="time" aria-label="Until" className="w-36" {...reg("quiet_hours_end")} />
              </div>
            </div>
          </>
        )}
      </fieldset>
      {canEdit && (
        <div>
          <Button type="submit" size="lg" disabled={isSubmitting || (!isDirty && !compact)}>
            {compact ? common("continue") : common("save")}
          </Button>
        </div>
      )}
    </form>
  );
}
