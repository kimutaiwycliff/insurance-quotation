import { getTranslations } from "next-intl/server";

import { BrandingEditor } from "@/components/settings/branding-editor";
import { SectionHeader } from "@/components/settings/section-header";

export const metadata = { title: "Documents & brand" };

export default async function BrandingPage() {
  const t = await getTranslations("settings");
  return (
    <>
      <SectionHeader title={t("branding")} description="How your quotes, invoices and receipts look to clients. The preview updates as you change things." />
      <BrandingEditor />
    </>
  );
}
