import { InvoiceDetail } from "@/components/billing/invoice-detail";

export default async function SalesQuotePage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  return <InvoiceDetail documentId={id} />;
}
