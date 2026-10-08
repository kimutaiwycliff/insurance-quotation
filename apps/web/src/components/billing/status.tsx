import { Badge } from "@/components/ui/badge";

const LABELS: Record<string, string> = {
  draft: "Draft",
  open: "Unpaid",
  partially_paid: "Part paid",
  paid: "Paid",
  overdue: "Overdue",
  issued: "Issued",
  sent: "Awaiting answer",
  accepted: "Accepted",
  declined: "Declined",
  expired: "Expired",
  invoiced: "Invoiced",
  void: "Void",
};

export function BillingStatus({ status }: { status: string }) {
  const variant =
    status === "paid" || status === "accepted" || status === "invoiced" ? "default" : status === "overdue" || status === "declined" || status === "expired" ? "destructive" : status === "draft" || status === "void" ? "secondary" : "outline";
  return <Badge variant={variant}>{LABELS[status] ?? status}</Badge>;
}

export const METHOD_LABELS: Record<string, string> = { mpesa: "M-Pesa", bank: "Bank transfer", card: "Card", cheque: "Cheque", cash: "Cash", other: "Other" };
