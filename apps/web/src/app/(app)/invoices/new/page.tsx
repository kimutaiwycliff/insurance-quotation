import { redirect } from "next/navigation";

import { InvoiceEditor } from "@/components/billing/invoice-editor";

export const metadata = { title: "New invoice" };

export default async function NewInvoicePage({ searchParams }: { searchParams: Promise<{ client?: string }> }) {
  const { client } = await searchParams;
  if (!client) redirect("/clients");
  return <InvoiceEditor clientId={client} />;
}
