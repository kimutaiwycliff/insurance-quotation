import { getTranslations } from "next-intl/server";

import { NumberingPanel } from "@/components/settings/numbering-panel";
import { SectionHeader } from "@/components/settings/section-header";

export const metadata = { title: "Document numbers" };

export default async function NumberingPage() {
  const t = await getTranslations("settings");
  const n = await getTranslations("numbering");
  return (
    <>
      <SectionHeader title={t("numbering")} description={n("body")} />
      <NumberingPanel />
    </>
  );
}
