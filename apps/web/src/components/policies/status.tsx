import { Badge } from "@/components/ui/badge";

const LABELS: Record<string, string> = {
  pending: "Awaiting cover",
  active: "Active",
  expired: "Expired",
  cancelled: "Cancelled",
};

export const STAGE_LABELS: Record<string, string> = {
  due: "To contact",
  contacted: "Contacted",
  quoted: "Quoted",
  renewed: "Renewed",
  lost: "Lost",
};

export function PolicyStatus({ status }: { status: string }) {
  const variant = status === "active" ? "default" : status === "pending" ? "outline" : status === "expired" ? "destructive" : "secondary";
  return <Badge variant={variant}>{LABELS[status] ?? status}</Badge>;
}

/** "in 12 days", "today", "3 days ago": for expiry dates. */
export function expiryText(days: number): string {
  if (days === 0) return "today";
  if (days > 0) return `in ${days} ${days === 1 ? "day" : "days"}`;
  return `${-days} ${days === -1 ? "day" : "days"} ago`;
}
