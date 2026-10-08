import { ItemsPanel } from "@/components/billing/items-panel";
import { SectionHeader } from "@/components/settings/section-header";

export const metadata = { title: "Items & prices" };

export default function ItemsPage() {
  return (
    <>
      <SectionHeader title="Items & prices" description="Products and services you invoice, with their usual price and tax." />
      <ItemsPanel />
    </>
  );
}
