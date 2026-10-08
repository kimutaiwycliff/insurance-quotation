"use client";

import { useQuery, useQueryClient } from "@tanstack/react-query";
import { FileText, Mail, MessageCircle, Phone } from "lucide-react";
import { useTranslations } from "next-intl";
import { useRef, useState, type FormEvent } from "react";
import { toast } from "sonner";

import Link from "next/link";

import { ClientForm, fromClient, toUpdate } from "@/components/clients/client-form";
import { ClientBilling } from "@/components/billing/client-billing";
import { PoliciesList } from "@/components/policies/policies-list";
import { QuotesList } from "@/components/quotes/quotes-list";
import { TaskList } from "@/components/tasks/task-list";
import { Field } from "@/components/forms/field";
import { useCan } from "@/components/shell/me-context";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { NativeSelect } from "@/components/ui/native-select";
import { Sheet, SheetContent, SheetDescription, SheetHeader, SheetTitle } from "@/components/ui/sheet";
import { Skeleton } from "@/components/ui/skeleton";
import { Textarea } from "@/components/ui/textarea";
import { ifMatch } from "@/lib/api/fetcher";
import {
  clientsActivitiesAdd,
  clientsRevealIdNumber,
  clientsUpdate,
  getClientsGetQueryKey,
  getClientsTimelineQueryKey,
  useClientsGet,
  useClientsTimeline,
} from "@/lib/api/generated/clients/clients";
import { documentsDownload, documentsList, getDocumentsListQueryKey } from "@/lib/api/generated/documents/documents";
import type { ActivityInKind, ClientOut, DocumentCreateCategory } from "@/lib/api/generated/model";
import { formatDate, formatPhone, relativeTime, whatsappLink } from "@/lib/format";
import { ApiError, problemMessage } from "@/lib/problem";
import { uploadDocument } from "@/lib/upload";
import { cn } from "@/lib/utils";

type Tab = "overview" | "timeline" | "quotes" | "policies" | "billing" | "documents" | "tasks";

function Overview({ client }: { client: ClientOut }) {
  const t = useTranslations("clients");
  const [idNumber, setIdNumber] = useState<string | null>(null);
  const canWrite = useCan("client:write");
  const rows: [string, string | null | undefined][] = [
    [t("phone"), formatPhone(client.phone)],
    [t("altPhone"), formatPhone(client.alt_phone)],
    [t("email"), client.email],
    [t("kraPin"), client.kra_pin],
    [t("idNumber"), idNumber ?? client.id_number_hint],
    [t("dob"), client.date_of_birth ? formatDate(client.date_of_birth) : null],
    [t("town"), (client.address as { town?: string }).town],
    [t("occupation"), client.occupation],
    [t("preferredChannel"), t(client.preferred_channel as "whatsapp")],
  ];
  return (
    <div className="grid gap-6">
      <dl className="grid gap-x-8 gap-y-3 sm:grid-cols-2">
        {rows.filter(([, v]) => v).map(([label, value]) => (
          <div key={label}>
            <dt className="text-sm text-muted-foreground">{label}</dt>
            <dd className="tabular font-bold break-words">{value}</dd>
          </div>
        ))}
      </dl>
      {client.id_number_hint && !idNumber && canWrite && (
        <div>
          <Button
            variant="outline"
            size="sm"
            onClick={async () => setIdNumber((await clientsRevealIdNumber(client.id)).id_number ?? null)}
          >
            {t("showId")}
          </Button>
        </div>
      )}
      {client.notes && (
        <div>
          <p className="text-sm text-muted-foreground">{t("notes")}</p>
          <p className="max-w-prose whitespace-pre-line">{client.notes}</p>
        </div>
      )}
    </div>
  );
}

const ACTIVITY_KINDS: ActivityInKind[] = ["call", "whatsapp", "meeting", "visit", "note"];

function Timeline({ clientId }: { clientId: string }) {
  const t = useTranslations("clients");
  const queryClient = useQueryClient();
  const timeline = useClientsTimeline(clientId);
  const canWrite = useCan("client:write");
  const [kind, setKind] = useState<ActivityInKind>("call");
  const [body, setBody] = useState("");

  async function log(event: FormEvent) {
    event.preventDefault();
    await clientsActivitiesAdd(clientId, { kind, body });
    setBody("");
    await queryClient.invalidateQueries({ queryKey: getClientsTimelineQueryKey(clientId) });
  }

  return (
    <div className="grid gap-6">
      {canWrite && (
        <form onSubmit={log} className="grid gap-3 rounded-lg border bg-card p-4">
          <div className="flex flex-wrap gap-1" role="radiogroup" aria-label="Activity type">
            {ACTIVITY_KINDS.map((k) => (
              <button
                key={k}
                type="button"
                role="radio"
                aria-checked={kind === k}
                onClick={() => setKind(k)}
                className={cn("rounded-full border px-3 py-1 text-sm", kind === k && "border-primary bg-primary text-primary-foreground")}
              >
                {k === "whatsapp" ? t("whatsapp") : k === "call" ? t("call") : t(k)}
              </button>
            ))}
          </div>
          <Textarea aria-label={t("activityPlaceholder")} placeholder={t("activityPlaceholder")} rows={2} value={body} onChange={(e) => setBody(e.target.value)} />
          <div>
            <Button type="submit" disabled={!body.trim()}>{t("logActivity")}</Button>
          </div>
        </form>
      )}
      {timeline.data?.length === 0 && <p className="text-muted-foreground">{t("noTimeline")}</p>}
      <ol className="grid gap-0 border-l-2 border-border pl-5">
        {(timeline.data ?? []).map((item, i) => (
          <li key={`${item.at}-${i}`} className="relative pb-5">
            <span aria-hidden="true" className={cn("absolute top-1.5 -left-[1.6rem] size-2.5 rounded-full", item.kind === "activity" ? "bg-maize" : "bg-border")} />
            <p className="font-bold">{item.title}</p>
            {item.detail && <p className="max-w-prose whitespace-pre-line">{item.detail}</p>}
            <p className="text-sm text-muted-foreground">{relativeTime(item.at)}</p>
          </li>
        ))}
      </ol>
    </div>
  );
}

const CATEGORIES: DocumentCreateCategory[] = ["kyc_id", "kyc_pin", "vehicle_logbook", "policy_schedule", "certificate", "claim", "other"];
const CATEGORY_LABELS: Record<string, string> = {
  kyc_id: "ID or passport copy",
  kyc_pin: "KRA PIN certificate",
  kyc_other: "Other KYC",
  vehicle_logbook: "Vehicle logbook",
  policy_schedule: "Policy schedule",
  certificate: "Certificate",
  claim: "Claim document",
  generated: "Generated",
  branding: "Branding",
  other: "Other",
};

function Documents({ clientId }: { clientId: string }) {
  const t = useTranslations("clients");
  const queryClient = useQueryClient();
  const canWrite = useCan("document:write");
  const params = { entity_type: "client", entity_id: clientId };
  const docs = useQuery({
    queryKey: [...getDocumentsListQueryKey(params)],
    queryFn: ({ signal }) => documentsList(params, { signal }),
  });
  const [category, setCategory] = useState<DocumentCreateCategory>("kyc_id");
  const [expires, setExpires] = useState("");
  const [busy, setBusy] = useState(false);
  const input = useRef<HTMLInputElement>(null);

  async function onFile(file: File | undefined) {
    if (!file) return;
    setBusy(true);
    try {
      await uploadDocument(file, category, CATEGORY_LABELS[category], {
        links: [{ entity_type: "client", entity_id: clientId }],
        expires_on: expires || undefined,
      });
      await queryClient.invalidateQueries({ queryKey: getDocumentsListQueryKey(params) });
      setExpires("");
    } catch (error) {
      toast.error(error instanceof ApiError ? problemMessage(error.problem) : "The file did not upload. Try again.");
    } finally {
      setBusy(false);
    }
  }

  async function open(id: string) {
    const { url } = await documentsDownload(id, { inline: true });
    window.open(url, "_blank", "noopener");
  }

  return (
    <div className="grid gap-6">
      {canWrite && (
        <div className="grid gap-3 rounded-lg border bg-card p-4 sm:grid-cols-[minmax(0,1fr)_10rem_auto] sm:items-end">
          <Field label={t("category")}>
            {(p) => (
              <NativeSelect {...p} value={category} onChange={(e) => setCategory(e.target.value as DocumentCreateCategory)}>
                {CATEGORIES.map((c) => <option key={c} value={c}>{CATEGORY_LABELS[c]}</option>)}
              </NativeSelect>
            )}
          </Field>
          <Field label={t("expires")} optional>
            {(p) => <Input {...p} type="date" value={expires} onChange={(e) => setExpires(e.target.value)} />}
          </Field>
          <input ref={input} type="file" className="sr-only" accept=".pdf,.png,.jpg,.jpeg,.webp,.heic" aria-label={t("uploadDocument")} onChange={(e) => onFile(e.target.files?.[0])} />
          <Button onClick={() => input.current?.click()} disabled={busy}>{busy ? "…" : t("uploadDocument")}</Button>
        </div>
      )}
      {docs.data?.items.length === 0 && <p className="text-muted-foreground">{t("noDocuments")}</p>}
      <ul className="divide-y rounded-lg border bg-card">
        {(docs.data?.items ?? []).map((d) => (
          <li key={d.id}>
            <button type="button" onClick={() => open(d.id)} className="flex w-full items-center gap-3 px-4 py-3 text-left hover:bg-accent">
              <FileText className="size-5 text-primary" aria-hidden="true" />
              <span className="flex-1">
                <span className="block font-bold">{CATEGORY_LABELS[d.category] ?? d.title}</span>
                <span className="text-sm text-muted-foreground">{formatDate(d.created_at)}</span>
              </span>
              {d.expires_on && <Badge variant={new Date(d.expires_on) < new Date() ? "destructive" : "outline"}>{t("expires")} {formatDate(d.expires_on)}</Badge>}
            </button>
          </li>
        ))}
      </ul>
    </div>
  );
}

export function ClientDetail({ clientId }: { clientId: string }) {
  const t = useTranslations("clients");
  const queryClient = useQueryClient();
  const client = useClientsGet(clientId);
  const canWrite = useCan("client:write");
  const canInvoice = useCan("invoice:write");
  const [tab, setTab] = useState<Tab>("overview");
  const [editing, setEditing] = useState(false);

  if (!client.data) return <Skeleton className="h-96 w-full" />;
  const c = client.data;
  const tabs: Tab[] = ["overview", "timeline", "quotes", "policies", ...(canInvoice ? (["billing"] as const) : []), "documents", "tasks"];

  return (
    <div className="grid gap-6">
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <h1 className="text-3xl">{c.display_name}</h1>
          <div className="mt-2 flex flex-wrap gap-1">
            {c.status === "archived" && <Badge variant="destructive">{t("archived")}</Badge>}
            {c.tags.map((tag) => <Badge key={tag} variant="secondary">{tag}</Badge>)}
          </div>
        </div>
        <div className="flex flex-wrap gap-2">
          {c.phone && (
            <>
              <Button asChild variant="outline"><a href={`tel:${c.phone}`}><Phone aria-hidden="true" /> {t("callAction")}</a></Button>
              <Button asChild variant="outline"><a href={whatsappLink(c.phone)} target="_blank" rel="noopener noreferrer"><MessageCircle aria-hidden="true" /> {t("whatsappAction")}</a></Button>
            </>
          )}
          {c.email && <Button asChild variant="outline"><a href={`mailto:${c.email}`}><Mail aria-hidden="true" /> {t("emailAction")}</a></Button>}
          {canWrite && <Button asChild variant="outline"><Link href={`/quotes/new?client=${c.id}`}>New quote</Link></Button>}
          {canWrite && <Button asChild variant="outline"><Link href={`/policies/new?client=${c.id}`}>Add policy</Link></Button>}
          {canInvoice && <Button asChild variant="outline"><Link href={`/invoices/new?client=${c.id}`}>New invoice</Link></Button>}
          {canWrite && <Button onClick={() => setEditing(true)}>{t("edit")}</Button>}
        </div>
      </div>

      <div role="tablist" aria-label={c.display_name} className="-mx-4 flex gap-1 overflow-x-auto border-b px-4 sm:mx-0 sm:px-0">
        {tabs.map((key) => (
          <button
            key={key}
            role="tab"
            type="button"
            id={`tab-${key}`}
            aria-selected={tab === key}
            aria-controls={`panel-${key}`}
            onClick={() => setTab(key)}
            className={cn("-mb-px border-b-[3px] border-transparent px-3 py-2 whitespace-nowrap", tab === key && "border-maize font-bold")}
          >
            {t(key)}
          </button>
        ))}
      </div>
      <div role="tabpanel" id={`panel-${tab}`} aria-labelledby={`tab-${tab}`}>
        {tab === "overview" && <Overview client={c} />}
        {tab === "timeline" && <Timeline clientId={c.id} />}
        {tab === "quotes" && <QuotesList clientId={c.id} />}
        {tab === "policies" && <PoliciesList clientId={c.id} />}
        {tab === "billing" && <ClientBilling clientId={c.id} />}
        {tab === "documents" && <Documents clientId={c.id} />}
        {tab === "tasks" && <TaskList entity={{ entity_type: "client", entity_id: c.id, label: c.display_name }} />}
      </div>

      <Sheet open={editing} onOpenChange={setEditing}>
        <SheetContent className="w-full overflow-y-auto sm:max-w-xl">
          <SheetHeader>
            <SheetTitle>{t("edit")}</SheetTitle>
            <SheetDescription className="sr-only">{c.display_name}</SheetDescription>
          </SheetHeader>
          <div className="grid gap-6 px-4 pb-8">
            <ClientForm
              clientId={c.id}
              initial={fromClient(c)}
              submitLabel={t("save")}
              onSubmit={async (values, dirty) => {
                const saved = await clientsUpdate(c.id, toUpdate(values, dirty), ifMatch(c.version));
                queryClient.setQueryData(getClientsGetQueryKey(c.id), saved);
                toast.success(t("saved"));
                setEditing(false);
              }}
            />
            {c.status === "active" && (
              <Button
                variant="ghost"
                className="justify-self-start text-destructive"
                onClick={async () => {
                  const saved = await clientsUpdate(c.id, { archived: true }, ifMatch(c.version));
                  queryClient.setQueryData(getClientsGetQueryKey(c.id), saved);
                  setEditing(false);
                }}
              >
                {t("archive")}
              </Button>
            )}
          </div>
        </SheetContent>
      </Sheet>
    </div>
  );
}
