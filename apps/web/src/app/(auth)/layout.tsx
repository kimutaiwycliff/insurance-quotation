import { getTranslations } from "next-intl/server";
import type { ReactNode } from "react";

import { Seal } from "@/components/brand/seal";

export default async function AuthLayout({ children }: { children: ReactNode }) {
  const t = await getTranslations("authPanel");
  return (
    <div className="grid min-h-dvh lg:grid-cols-[minmax(0,5fr)_minmax(0,6fr)]">
      <aside className="relative hidden overflow-hidden bg-ink p-12 text-[#f6f7f4] lg:flex lg:flex-col lg:justify-between">
        <p className="font-heading text-xl font-bold">BrokerOS</p>
        <div className="max-w-md">
          <Seal name="Your agency name" size={168} className="mb-10" />
          <h1 className="text-4xl leading-tight">{t("heading")}</h1>
          <p className="mt-4 max-w-prose text-lg text-[#c9d6d1]">{t("body")}</p>
        </div>
        <div aria-hidden="true" className="h-1 w-24 bg-maize" />
      </aside>
      <main className="flex items-start justify-center px-5 py-10 sm:items-center sm:px-8">
        <div className="w-full max-w-sm">
          <p className="mb-8 font-heading text-lg font-bold lg:hidden">BrokerOS</p>
          {children}
        </div>
      </main>
    </div>
  );
}
