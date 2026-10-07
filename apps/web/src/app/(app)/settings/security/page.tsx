import { getTranslations } from "next-intl/server";

import { SectionHeader } from "@/components/settings/section-header";
import { SecurityPanel } from "@/components/settings/security-panel";

export const metadata = { title: "Security" };

export default async function SecurityPage() {
  const t = await getTranslations("settings");
  return (
    <>
      <SectionHeader title={t("security")} />
      <SecurityPanel />
    </>
  );
}
