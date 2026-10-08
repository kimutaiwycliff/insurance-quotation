import { redirect } from "next/navigation";

import { NewPolicy, PolicyFromQuote } from "@/components/policies/new-policy";

export const metadata = { title: "New policy" };

export default async function NewPolicyPage({ searchParams }: { searchParams: Promise<{ client?: string; quote?: string; renew?: string }> }) {
  const { client, quote, renew } = await searchParams;
  if (quote) return <PolicyFromQuote quoteId={quote} />;
  if (!client) redirect("/clients");
  return <NewPolicy clientId={client} renewalOf={renew} />;
}
