import { TaxSettings } from "@/components/billing/etims";
import { SectionHeader } from "@/components/settings/section-header";

export const metadata = { title: "Tax & eTIMS" };

export default function TaxSettingsPage() {
  return (
    <>
      <SectionHeader title="Tax & eTIMS" description="Whether your invoices carry KRA eTIMS details." />
      <TaxSettings />
    </>
  );
}
