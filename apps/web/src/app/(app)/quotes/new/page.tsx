import { redirect } from "next/navigation";

import { NewQuote } from "@/components/quotes/new-quote";

export const metadata = { title: "New quote" };

export default async function NewQuotePage({ searchParams }: { searchParams: Promise<{ client?: string }> }) {
  const { client } = await searchParams;
  if (!client) redirect("/clients");
  return <NewQuote clientId={client} />;
}
