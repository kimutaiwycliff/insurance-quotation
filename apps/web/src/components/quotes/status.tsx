import { Badge } from "@/components/ui/badge";

const LABELS: Record<string, string> = {
  draft: "Draft",
  sent: "Sent",
  accepted: "Accepted",
  declined: "Declined",
  withdrawn: "Withdrawn",
  expired: "Expired",
};

export function QuoteStatus({ status }: { status: string }) {
  const variant = status === "accepted" ? "default" : status === "declined" || status === "expired" ? "destructive" : status === "sent" ? "outline" : "secondary";
  return <Badge variant={variant}>{LABELS[status] ?? status}</Badge>;
}
