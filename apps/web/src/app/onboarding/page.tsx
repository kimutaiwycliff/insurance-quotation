import { redirect } from "next/navigation";

import { OnboardingWizard } from "@/components/onboarding/wizard";
import type { Me } from "@/lib/me";
import { serverApi } from "@/lib/server/api";
import { getSession } from "@/lib/server/session";

export const metadata = { title: "Set up your agency" };

export default async function OnboardingPage({ searchParams }: { searchParams: Promise<{ step?: string }> }) {
  const session = await getSession();
  if (!session) redirect("/sign-in?next=/onboarding");
  const { step } = await searchParams;
  const later = step === "details" || step === "brand";
  if (later && session.session.activeOrganizationId) {
    const me = await serverApi<Me>("/api/v1/me");
    return <OnboardingWizard step={step} me={me} userName={session.user.name} />;
  }
  return <OnboardingWizard step="agency" me={null} userName={session.user.name} />;
}
