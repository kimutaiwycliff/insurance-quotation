"use client";

import { useQueryClient } from "@tanstack/react-query";
import { Mail, MessageCircle, Settings2 } from "lucide-react";
import Link from "next/link";
import { useState } from "react";
import { toast } from "sonner";

import { FormError } from "@/components/forms/field";
import { expiryText, STAGE_LABELS } from "@/components/policies/status";
import { QuoteStatus } from "@/components/quotes/status";
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
import { Skeleton } from "@/components/ui/skeleton";
import { Switch } from "@/components/ui/switch";
import { Textarea } from "@/components/ui/textarea";
import { ifMatch } from "@/lib/api/fetcher";
import type { RenewalColumnStage, RenewalItem } from "@/lib/api/generated/model";
import {
  getOrganizationGetQueryKey,
  organizationUpdate,
  useOrganizationGet,
} from "@/lib/api/generated/organization/organization";
import {
  getRenewalsBoardQueryKey,
  policiesRemind,
  policiesRenewalStage,
  useRenewalsBoard,
} from "@/lib/api/generated/policies/policies";
import { formatDate, formatMoney } from "@/lib/format";
import { ApiError, problemMessage } from "@/lib/problem";
import { cn } from "@/lib/utils";

const STAGES: RenewalColumnStage[] = ["due", "contacted", "quoted", "renewed", "lost"];
const WINDOWS = [30, 60, 90];

function RenewalCard({
  item,
  focused,
  onChanged,
}: {
  item: RenewalItem;
  focused: boolean;
  onChanged: () => Promise<unknown>;
}) {
  const canWrite = useCan("client:write");
  const [busy, setBusy] = useState(false);
  const [losing, setLosing] = useState(false);
  const [reason, setReason] = useState("");
  const open = !["renewed", "lost"].includes(item.renewal_stage);
  const urgent = item.days_to_expiry <= 7;

  async function act(fn: () => Promise<unknown>, success?: string) {
    setBusy(true);
    try {
      await fn();
      await onChanged();
      if (success) toast.success(success);
    } catch (e) {
      toast.error(
        e instanceof ApiError ? problemMessage(e.problem) : "That did not work. Try again.",
      );
    } finally {
      setBusy(false);
    }
  }

  return (
    <li
      id={`renewal-${item.id}`}
      className={cn("bg-card grid gap-2 rounded-md border p-3", focused && "ring-primary ring-2")}
    >
      <div>
        <Link href={`/policies/${item.id}`} className="font-bold hover:underline">
          {item.client.display_name}
        </Link>
        <p className="text-sm">{item.description}</p>
        <p className="text-muted-foreground text-sm">
          {item.insurer_name} · {formatMoney(item.total_premium, item.currency)}
        </p>
      </div>
      <p
        className={cn(
          "text-sm",
          open && urgent ? "text-destructive font-bold" : "text-muted-foreground",
        )}
      >
        {item.days_to_expiry < 0 ? "Expired" : "Expires"} {formatDate(item.end_date)} (
        {expiryText(item.days_to_expiry)})
      </p>
      {item.last_contacted_at && (
        <p className="text-muted-foreground text-sm">
          Last contacted {formatDate(item.last_contacted_at)}
        </p>
      )}
      {item.renewal_quote_id && (
        <p className="flex items-center gap-2 text-sm">
          <Link className="text-primary hover:underline" href={`/quotes/${item.renewal_quote_id}`}>
            Renewal quote
          </Link>
          {item.renewal_quote_status && <QuoteStatus status={item.renewal_quote_status} />}
        </p>
      )}
      {item.renewal_stage === "lost" && item.lost_reason && (
        <p className="text-muted-foreground text-sm">{item.lost_reason}</p>
      )}
      {canWrite && open && (
        <div className="flex flex-wrap gap-1.5">
          {item.whatsapp_url && (
            <Button asChild size="sm" variant="outline">
              <a
                href={item.whatsapp_url}
                target="_blank"
                rel="noopener noreferrer"
                onClick={() => void act(() => policiesRemind(item.id, { channel: "whatsapp" }))}
              >
                <MessageCircle aria-hidden="true" /> WhatsApp
              </a>
            </Button>
          )}
          {item.client.email && (
            <Button
              size="sm"
              variant="outline"
              disabled={busy}
              onClick={() =>
                act(
                  () => policiesRemind(item.id, { channel: "email" }),
                  `Reminder emailed to ${item.client.email}`,
                )
              }
            >
              <Mail aria-hidden="true" /> Email
            </Button>
          )}
          {!item.renewal_quote_id && (
            <Button asChild size="sm">
              <Link href={`/quotes/new?client=${item.client.id}&renew=${item.id}`}>
                Quote renewal
              </Link>
            </Button>
          )}
          <Button asChild size="sm" variant="ghost">
            <Link href={`/policies/new?client=${item.client.id}&renew=${item.id}`}>
              Record renewal
            </Link>
          </Button>
          <Button
            size="sm"
            variant="ghost"
            className="text-destructive"
            onClick={() => setLosing(true)}
          >
            Lost
          </Button>
        </div>
      )}
      {canWrite && item.renewal_stage === "lost" && (
        <Button
          size="sm"
          variant="ghost"
          className="justify-self-start"
          disabled={busy}
          onClick={() => act(() => policiesRenewalStage(item.id, { stage: "due" }))}
        >
          Reopen
        </Button>
      )}
      <Dialog open={losing} onOpenChange={setLosing}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Renewal lost: {item.client.display_name}</DialogTitle>
            <DialogDescription>
              Why is the client not renewing {item.description}?
            </DialogDescription>
          </DialogHeader>
          <Textarea
            aria-label="Reason"
            rows={3}
            value={reason}
            onChange={(e) => setReason(e.target.value)}
            placeholder="e.g. Sold the car, or went to another agent"
          />
          <DialogFooter>
            <Button
              disabled={busy || !reason.trim()}
              onClick={async () => {
                await act(() =>
                  policiesRenewalStage(item.id, { stage: "lost", lost_reason: reason.trim() }),
                );
                setLosing(false);
              }}
            >
              Mark as lost
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </li>
  );
}

function ReminderSettings({
  open,
  onOpenChange,
}: {
  open: boolean;
  onOpenChange: (o: boolean) => void;
}) {
  const queryClient = useQueryClient();
  const org = useOrganizationGet();
  const [days, setDays] = useState<string | null>(null);
  const [emails, setEmails] = useState<boolean | null>(null);
  const [error, setError] = useState<string | null>(null);
  if (!org.data) return null;
  const currentDays = days ?? org.data.renewal_reminder_days.join(", ");
  const currentEmails = emails ?? org.data.renewal_client_emails;

  async function save() {
    const parsed = currentDays
      .split(/[,\s]+/)
      .filter(Boolean)
      .map(Number);
    if (parsed.length === 0 || parsed.some((d) => !Number.isInteger(d) || d < 1 || d > 120)) {
      setError("Enter whole numbers of days between 1 and 120, e.g. 30, 14, 7");
      return;
    }
    try {
      const saved = await organizationUpdate(
        { renewal_reminder_days: parsed, renewal_client_emails: currentEmails },
        ifMatch(org.data!.version),
      );
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
          <DialogTitle>Renewal reminders</DialogTitle>
          <DialogDescription>
            Each morning we remind the agent who looks after a policy as its expiry gets close.
          </DialogDescription>
        </DialogHeader>
        <div className="grid gap-4">
          <FormError message={error} />
          <label className="grid gap-1.5">
            <span className="text-sm font-bold">Days before expiry</span>
            <Input
              value={currentDays}
              onChange={(e) => setDays(e.target.value)}
              aria-describedby="days-hint"
            />
            <span id="days-hint" className="text-muted-foreground text-sm">
              Separate with commas, up to six. For example: 30, 14, 7
            </span>
          </label>
          <label className="flex items-start justify-between gap-4">
            <span>
              <span className="block font-bold">Also email the client</span>
              <span className="text-muted-foreground text-sm">
                A short reminder with your phone number. Clients can unsubscribe.
              </span>
            </span>
            <Switch
              checked={currentEmails}
              onCheckedChange={setEmails}
              aria-label="Also email the client"
            />
          </label>
        </div>
        <DialogFooter>
          <Button onClick={save}>Save</Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

export function RenewalsBoard({ focus }: { focus?: string }) {
  const queryClient = useQueryClient();
  const canSettings = useCan("org:update");
  const [windowDays, setWindowDays] = useState(60);
  const [mobileStage, setMobileStage] = useState<RenewalColumnStage>("due");
  const [settings, setSettings] = useState(false);
  const board = useRenewalsBoard({ window_days: windowDays });
  const refresh = () =>
    queryClient.invalidateQueries({
      queryKey: getRenewalsBoardQueryKey({ window_days: windowDays }),
    });
  const column = (stage: RenewalColumnStage) => board.data?.columns.find((c) => c.stage === stage);

  return (
    <div className="grid gap-5">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h1 className="text-3xl">Renewals</h1>
          <p className="text-muted-foreground mt-1">
            Active policies ending in the next {windowDays} days, and those that ended in the last
            30.
          </p>
        </div>
        <div className="flex items-center gap-2">
          <NativeSelect
            aria-label="Show policies ending within"
            value={String(windowDays)}
            onChange={(e) => setWindowDays(Number(e.target.value))}
            className="w-36"
          >
            {WINDOWS.map((w) => (
              <option key={w} value={w}>
                Next {w} days
              </option>
            ))}
          </NativeSelect>
          {canSettings && (
            <Button
              variant="outline"
              size="icon"
              aria-label="Reminder settings"
              onClick={() => setSettings(true)}
            >
              <Settings2 />
            </Button>
          )}
        </div>
      </div>

      <div
        role="tablist"
        aria-label="Stages"
        className="-mx-4 flex gap-1 overflow-x-auto px-4 md:hidden"
      >
        {STAGES.map((s) => (
          <button
            key={s}
            role="tab"
            type="button"
            aria-selected={mobileStage === s}
            onClick={() => setMobileStage(s)}
            className={cn(
              "rounded-full border px-3 py-1.5 text-sm whitespace-nowrap",
              mobileStage === s && "border-primary bg-primary text-primary-foreground",
            )}
          >
            {STAGE_LABELS[s]} <span className="tabular">{column(s)?.count ?? 0}</span>
          </button>
        ))}
      </div>

      {!board.data ? (
        <Skeleton className="h-96 w-full" />
      ) : (
        <div className="grid gap-4 md:grid-cols-5">
          {STAGES.map((stage) => {
            const items = board.data.items.filter((i) => i.renewal_stage === stage);
            const c = column(stage);
            return (
              <section
                key={stage}
                aria-labelledby={`stage-${stage}`}
                className={cn(
                  "grid content-start gap-2",
                  mobileStage !== stage && "hidden md:grid",
                )}
              >
                <header
                  className={cn(
                    "border-b-[3px] pb-1",
                    stage === "lost" ? "border-border" : "border-maize",
                  )}
                >
                  <h2 id={`stage-${stage}`} className="text-lg">
                    {STAGE_LABELS[stage]}{" "}
                    <span className="tabular text-muted-foreground">{c?.count ?? 0}</span>
                  </h2>
                  {c && Number(c.premium) > 0 && (
                    <p className="tabular text-muted-foreground text-sm">
                      {formatMoney(c.premium, board.data.currency)}
                    </p>
                  )}
                </header>
                {items.length === 0 ? (
                  <p className="text-muted-foreground py-4 text-sm">Nothing here.</p>
                ) : (
                  <ul className="grid gap-2">
                    {items.map((item) => (
                      <RenewalCard
                        key={item.id}
                        item={item}
                        focused={item.id === focus}
                        onChanged={refresh}
                      />
                    ))}
                  </ul>
                )}
              </section>
            );
          })}
        </div>
      )}
      {canSettings && <ReminderSettings open={settings} onOpenChange={setSettings} />}
    </div>
  );
}
