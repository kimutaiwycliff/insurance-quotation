import { getTranslations } from "next-intl/server";
import type { ReactNode } from "react";

import { SettingsNav } from "@/components/settings/settings-nav";

export default async function SettingsLayout({ children }: { children: ReactNode }) {
  const t = await getTranslations("settings");
  return (
    <div>
      <h1 className="mb-6 text-3xl">{t("title")}</h1>
      <div className="grid gap-6 md:grid-cols-[13rem_minmax(0,1fr)] md:gap-10">
        <SettingsNav />
        <div className="min-w-0">{children}</div>
      </div>
    </div>
  );
}
