import { InsurersPanel } from "@/components/insurers/insurers-panel";
import { SectionHeader } from "@/components/settings/section-header";

export const metadata = { title: "Insurers & products" };

export default function InsurersPage() {
  return (
    <>
      <SectionHeader title="Insurers & products" description="The insurers you place business with, their products, rates and your commission." />
      <InsurersPanel />
    </>
  );
}
