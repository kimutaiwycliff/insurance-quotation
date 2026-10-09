"use client";

import Link from "next/link";

import { useCan, useMe } from "@/components/shell/me-context";
import { useSubscriptionGet } from "@/lib/api/generated/subscription/subscription";
import { daysUntil, formatDate } from "@/lib/format";
import { cn } from "@/lib/utils";

const TRIAL_WARNING_DAYS = 7;

/** One line above every page when the plan needs attention: trial ending, payment due, or read-only. */
export function PlanBanner() {
  const me = useMe();
  const canRead = useCan("org:read");
  const canPay = useCan("org:update");
  const sub = useSubscriptionGet({ query: { enabled: canRead, staleTime: 5 * 60_000 } });
  const data = sub.data;
  let message: string | null = null;
  let urgent = false;
  if (me.read_only || data?.status === "read_only") {
    message = "Your plan has lapsed, so the account is read-only. You can see and download everything but not add or change anything.";
    urgent = true;
  } else if (data?.status === "past_due" && data.period_end) {
    message = `Your plan ended on ${formatDate(data.period_end)}. Pay within a few days to keep adding and changing things.`;
    urgent = true;
  } else if (data?.status === "trialing" && data.trial_ends_at) {
    const days = daysUntil(data.trial_ends_at);
    if (days <= TRIAL_WARNING_DAYS) {
      message = `Your free trial ends in ${days} ${days === 1 ? "day" : "days"}. Choose a plan to keep every feature.`;
    }
  }
  if (!message) return null;
  return (
    <div role="status" className={cn("flex flex-wrap items-center gap-x-3 gap-y-1 border-b px-4 py-2 text-sm sm:px-6", urgent ? "bg-destructive/10" : "bg-maize/20")}>
      <span>{message}</span>
      {canPay ? (
        <Link href="/settings/plan" className="font-bold underline underline-offset-2">
          {urgent ? "Pay now" : "See plans"}
        </Link>
      ) : (
        <span className="text-muted-foreground">Ask the account owner to pay.</span>
      )}
    </div>
  );
}
