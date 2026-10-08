import { MpesaSettings } from "@/components/billing/mpesa-settings";
import { SectionHeader } from "@/components/settings/section-header";

export const metadata = { title: "Payments" };

export default function PaymentsSettingsPage() {
  return (
    <>
      <SectionHeader title="Payments" description="How clients pay your invoices." />
      <MpesaSettings />
    </>
  );
}
