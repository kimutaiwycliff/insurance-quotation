import { Badge } from "@/components/ui/badge";

const LABELS: Record<string, string> = {
  draft: "Draft",
  open: "Unpaid",
  partially_paid: "Part paid",
  paid: "Paid",
  overdue: "Overdue",
  issued: "Issued",
  void: "Void",
};

export function BillingStatus({ status }: { status: string }) {
  const variant =
    status === "paid" ? "default" : status === "overdue" ? "destructive" : status === "draft" || status === "void" ? "secondary" : "outline";
  return <Badge variant={variant}>{LABELS[status] ?? status}</Badge>;
}

export const METHOD_LABELS: Record<string, string> = { mpesa: "M-Pesa", bank: "Bank transfer", card: "Card", cheque: "Cheque", cash: "Cash", other: "Other" };
