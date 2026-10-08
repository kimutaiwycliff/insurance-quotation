"use client";

import { zodResolver } from "@hookform/resolvers/zod";
import { useQueryClient } from "@tanstack/react-query";
import { MessageCircle, Plus } from "lucide-react";
import { useRouter } from "next/navigation";
import { useTranslations } from "next-intl";
import { useState } from "react";
import { useForm } from "react-hook-form";
import { toast } from "sonner";
import { z } from "zod";

import { Field, FormError } from "@/components/forms/field";
import { useCan } from "@/components/shell/me-context";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { NativeSelect } from "@/components/ui/native-select";
import { Sheet, SheetContent, SheetDescription, SheetHeader, SheetTitle } from "@/components/ui/sheet";
import { Skeleton } from "@/components/ui/skeleton";
import { Textarea } from "@/components/ui/textarea";
import { ifMatch } from "@/lib/api/fetcher";
import {
  getLeadsListQueryKey,
  getLeadsPipelineQueryKey,
  leadsConvert,
  leadsCreate,
  leadsUpdate,
  useLeadsList,
  useLeadsPipeline,
} from "@/lib/api/generated/leads/leads";
import type { LeadCreate, LeadOut, LeadOutStage } from "@/lib/api/generated/model";
import { formatDate, formatMoney, formatPhone, whatsappLink } from "@/lib/format";
import { applyApiError } from "@/lib/forms";
import { ApiError, problemMessage } from "@/lib/problem";
import { cn } from "@/lib/utils";

type Interest = NonNullable<LeadCreate["interests"]>[number];
const STAGES: LeadOutStage[] = ["new", "contacted", "quoted", "won", "lost"];
const INTERESTS: Interest[] = ["motor", "medical", "life", "home", "business", "travel", "education"];

const leadSchema = z
  .object({
    name: z.string().trim().min(1, "Enter a name").max(200),
    phone: z.string().trim().max(30).optional(),
    email: z.email("Enter a valid email address").optional().or(z.literal("")),
    interests: z.array(z.string()),
    estimate: z.string().regex(/^(\d{1,12}(\.\d{1,2})?)?$/, "Enter an amount like 45000").optional(),
    follow_up: z.string().optional(),
    notes: z.string().max(5000).optional(),
  })
  .refine((v) => v.phone || v.email, { path: ["phone"], message: "Add a phone number or an email" });
type LeadValues = z.input<typeof leadSchema>;

function AddLead({ currency, onDone }: { currency: string; onDone: () => void }) {
  const t = useTranslations("leads");
  const form = useForm<LeadValues>({ resolver: zodResolver(leadSchema), defaultValues: { interests: [] } });
  const { errors, isSubmitting } = form.formState;
  async function submit(v: LeadValues) {
    try {
      await leadsCreate({
        name: v.name,
        phone: v.phone || undefined,
        email: v.email || undefined,
        interests: v.interests as Interest[],
        estimated_premium: v.estimate ? { amount: v.estimate, currency } : undefined,
        next_follow_up_at: v.follow_up ? new Date(`${v.follow_up}T09:00:00`).toISOString() : undefined,
        notes: v.notes || undefined,
        source: "other",
      });
      toast.success(t("created"));
      onDone();
    } catch (error) {
      applyApiError(error, form.setError, ["name", "phone", "email"]);
    }
  }
  return (
    <form onSubmit={form.handleSubmit(submit)} noValidate className="grid gap-5">
      <FormError message={errors.root?.message} />
      <Field label={t("name")} error={errors.name?.message}>{(p) => <Input {...p} {...form.register("name")} />}</Field>
      <Field label="Phone" error={errors.phone?.message}>{(p) => <Input {...p} type="tel" inputMode="tel" placeholder="0712 345 678" {...form.register("phone")} />}</Field>
      <Field label="Email" optional error={errors.email?.message}>{(p) => <Input {...p} type="email" {...form.register("email")} />}</Field>
      <fieldset className="grid gap-2">
        <legend className="mb-1 text-sm font-bold">{t("interests")}</legend>
        <div className="flex flex-wrap gap-2">
          {INTERESTS.map((i) => (
            <label key={i} className="flex items-center gap-1.5 rounded-full border px-3 py-1 text-sm capitalize has-[:checked]:border-primary has-[:checked]:bg-primary has-[:checked]:text-primary-foreground">
              <input type="checkbox" value={i} className="sr-only" {...form.register("interests")} />
              {i}
            </label>
          ))}
        </div>
      </fieldset>
      <Field label={`${t("estimate")} (${currency})`} optional error={errors.estimate?.message}>
        {(p) => <Input {...p} inputMode="decimal" {...form.register("estimate")} />}
      </Field>
      <Field label={t("followUp")} optional>{(p) => <Input {...p} type="date" {...form.register("follow_up")} />}</Field>
      <Field label="Notes" optional>{(p) => <Textarea {...p} rows={3} {...form.register("notes")} />}</Field>
      <div><Button type="submit" size="lg" disabled={isSubmitting}>{t("add")}</Button></div>
    </form>
  );
}

function LeadCard({ lead, onChanged }: { lead: LeadOut; onChanged: () => Promise<void> }) {
  const t = useTranslations("leads");
  const router = useRouter();
  const canWrite = useCan("lead:write");
  const [busy, setBusy] = useState(false);
  const [losing, setLosing] = useState(false);
  const [reason, setReason] = useState("");

  async function act(fn: () => Promise<unknown>) {
    setBusy(true);
    try {
      await fn();
      await onChanged();
    } catch (error) {
      toast.error(error instanceof ApiError ? problemMessage(error.problem) : "That did not work. Try again.");
    } finally {
      setBusy(false);
    }
  }

  async function move(stage: LeadOutStage) {
    if (stage === lead.stage) return;
    if (stage === "won") {
      return act(async () => {
        const { client_id } = await leadsConvert(lead.id, {});
        toast.success(t("converted"));
        router.push(`/clients/${client_id}`);
      });
    }
    if (stage === "lost") return setLosing(true);
    return act(() => leadsUpdate(lead.id, { stage }, ifMatch(lead.version)));
  }

  const overdue = lead.next_follow_up_at && new Date(lead.next_follow_up_at) < new Date() && ["new", "contacted", "quoted"].includes(lead.stage);
  return (
    <li className="grid gap-2 rounded-md border bg-card p-3">
      <div className="flex items-start justify-between gap-2">
        <p className="font-bold">{lead.name}</p>
        {lead.estimated_premium && <span className="tabular text-sm">{formatMoney(lead.estimated_premium.amount, lead.estimated_premium.currency)}</span>}
      </div>
      {lead.interests.length > 0 && (
        <div className="flex flex-wrap gap-1">{lead.interests.map((i) => <Badge key={i} variant="secondary" className="capitalize">{i}</Badge>)}</div>
      )}
      {lead.phone && (
        <a href={whatsappLink(lead.phone)} target="_blank" rel="noopener noreferrer" className="flex items-center gap-1.5 text-sm text-primary hover:underline">
          <MessageCircle className="size-4" aria-hidden="true" /> {formatPhone(lead.phone)}
        </a>
      )}
      {lead.next_follow_up_at && (
        <p className={cn("text-sm", overdue ? "font-bold text-destructive" : "text-muted-foreground")}>
          {t("followUp")} {formatDate(lead.next_follow_up_at)}
        </p>
      )}
      {lead.stage === "lost" && lead.lost_reason && <p className="text-sm text-muted-foreground">{lead.lost_reason}</p>}
      {canWrite && lead.stage !== "won" && (
        <NativeSelect aria-label={`${t("moveTo")}: ${lead.name}`} value={lead.stage} disabled={busy} onChange={(e) => move(e.target.value as LeadOutStage)} className="h-9 text-sm">
          {STAGES.map((s) => <option key={s} value={s}>{s === "won" ? t("convert") : `${t("moveTo")} ${t(s)}`}</option>)}
        </NativeSelect>
      )}
      {lead.client_id && (
        <Button variant="link" className="h-auto justify-start p-0" onClick={() => router.push(`/clients/${lead.client_id}`)}>
          Open client
        </Button>
      )}
      <Dialog open={losing} onOpenChange={setLosing}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>{t("markLost")}: {lead.name}</DialogTitle>
            <DialogDescription>{t("lostReason")}</DialogDescription>
          </DialogHeader>
          <Textarea aria-label={t("lostReason")} value={reason} onChange={(e) => setReason(e.target.value)} rows={3} placeholder="e.g. Chose a cheaper insurer" />
          <DialogFooter>
            <Button
              disabled={!reason.trim() || busy}
              onClick={() =>
                act(async () => {
                  await leadsUpdate(lead.id, { stage: "lost", lost_reason: reason.trim() }, ifMatch(lead.version));
                  setLosing(false);
                })
              }
            >
              {t("markLost")}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </li>
  );
}

export function LeadsBoard({ currency }: { currency: string }) {
  const t = useTranslations("leads");
  const queryClient = useQueryClient();
  const canWrite = useCan("lead:write");
  const leads = useLeadsList();
  const pipeline = useLeadsPipeline();
  const [adding, setAdding] = useState(false);
  const [mobileStage, setMobileStage] = useState<LeadOutStage>("new");

  const refresh = async () => {
    await queryClient.invalidateQueries({ queryKey: getLeadsListQueryKey() });
    await queryClient.invalidateQueries({ queryKey: getLeadsPipelineQueryKey() });
  };
  const summary = (stage: LeadOutStage) => pipeline.data?.stages.find((s) => s.stage === stage);

  return (
    <div className="grid gap-5">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h1 className="text-3xl">{t("title")}</h1>
          {(pipeline.data?.follow_ups_due ?? 0) > 0 && (
            <p className="mt-1 font-bold text-destructive">{t("followUpsDue", { count: pipeline.data!.follow_ups_due })}</p>
          )}
        </div>
        {canWrite && <Button onClick={() => setAdding(true)}><Plus aria-hidden="true" /> {t("add")}</Button>}
      </div>

      <div role="tablist" aria-label="Stages" className="-mx-4 flex gap-1 overflow-x-auto px-4 md:hidden">
        {STAGES.map((s) => (
          <button key={s} role="tab" type="button" aria-selected={mobileStage === s} onClick={() => setMobileStage(s)}
            className={cn("rounded-full border px-3 py-1.5 text-sm whitespace-nowrap", mobileStage === s && "border-primary bg-primary text-primary-foreground")}>
            {t(s)} <span className="tabular">{summary(s)?.count ?? 0}</span>
          </button>
        ))}
      </div>

      {!leads.data ? (
        <Skeleton className="h-96 w-full" />
      ) : (
        <div className="grid gap-4 md:grid-cols-5">
          {STAGES.map((stage) => {
            const items = leads.data.filter((l) => l.stage === stage);
            const s = summary(stage);
            return (
              <section key={stage} aria-labelledby={`stage-${stage}`} className={cn("grid content-start gap-2", mobileStage !== stage && "hidden md:grid")}>
                <header className="border-b-[3px] border-maize pb-1 data-[stage=lost]:border-border" data-stage={stage}>
                  <h2 id={`stage-${stage}`} className="text-lg">{t(stage)} <span className="tabular text-muted-foreground">{s?.count ?? 0}</span></h2>
                  {s && Number(s.estimated_premium.amount) > 0 && (
                    <p className="tabular text-sm text-muted-foreground">{formatMoney(s.estimated_premium.amount, s.estimated_premium.currency)}</p>
                  )}
                </header>
                {items.length === 0 ? <p className="py-4 text-sm text-muted-foreground">{t("empty")}</p> : (
                  <ul className="grid gap-2">{items.map((lead) => <LeadCard key={lead.id} lead={lead} onChanged={refresh} />)}</ul>
                )}
              </section>
            );
          })}
        </div>
      )}

      <Sheet open={adding} onOpenChange={setAdding}>
        <SheetContent className="w-full overflow-y-auto sm:max-w-md">
          <SheetHeader>
            <SheetTitle>{t("add")}</SheetTitle>
            <SheetDescription className="sr-only">{t("add")}</SheetDescription>
          </SheetHeader>
          <div className="px-4 pb-8">
            <AddLead currency={currency} onDone={async () => { setAdding(false); await refresh(); }} />
          </div>
        </SheetContent>
      </Sheet>
    </div>
  );
}
