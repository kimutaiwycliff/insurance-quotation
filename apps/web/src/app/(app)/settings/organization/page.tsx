import { getTranslations } from "next-intl/server";

import { OrganizationForm } from "@/components/settings/organization-form";
import { SectionHeader } from "@/components/settings/section-header";

export const metadata = { title: "Agency profile" };

export default async function OrganizationPage() {
  const t = await getTranslations("settings");
  return (
    <>
      <SectionHeader title={t("organization")} description="Shown on your quotes, invoices and receipts." />
      <OrganizationForm />
    </>
  );
}
