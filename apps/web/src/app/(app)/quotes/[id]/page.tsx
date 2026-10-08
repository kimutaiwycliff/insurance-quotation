import { QuoteDetail } from "@/components/quotes/quote-detail";

export default async function QuotePage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  return <QuoteDetail quoteId={id} />;
}
