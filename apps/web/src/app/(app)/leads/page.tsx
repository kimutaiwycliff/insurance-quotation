import { LeadsBoard } from "@/components/leads/leads-board";
import type { OrganizationOut } from "@/lib/api/generated/model";
import { serverApi } from "@/lib/server/api";

export const metadata = { title: "Leads" };

export default async function LeadsPage() {
  const org = await serverApi<OrganizationOut>("/api/v1/organization");
  return <LeadsBoard currency={org.default_currency} />;
}
