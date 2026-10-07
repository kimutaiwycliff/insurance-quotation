import { getTranslations } from "next-intl/server";

import { MembersPanel } from "@/components/settings/members-panel";
import { SectionHeader } from "@/components/settings/section-header";

export const metadata = { title: "Team" };

export default async function MembersPage() {
  const t = await getTranslations("settings");
  return (
    <>
      <SectionHeader title={t("members")} description="Invite agents and office staff, and choose what each person can do." />
      <MembersPanel />
    </>
  );
}
