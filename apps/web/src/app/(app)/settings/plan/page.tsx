import { SectionHeader } from "@/components/settings/section-header";
import { PlanPanel } from "@/components/settings/plan-panel";

export const metadata = { title: "Plan & billing" };

export default function PlanSettingsPage() {
  return (
    <>
      <SectionHeader title="Plan & billing" description="Your plan, what you use and what you have paid." />
      <PlanPanel />
    </>
  );
}
