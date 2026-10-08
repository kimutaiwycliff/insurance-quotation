import { QuotesList } from "@/components/quotes/quotes-list";

export const metadata = { title: "Quotes" };

export default function QuotesPage() {
  return (
    <div className="grid gap-5">
      <h1 className="text-3xl">Quotes</h1>
      <QuotesList />
    </div>
  );
}
