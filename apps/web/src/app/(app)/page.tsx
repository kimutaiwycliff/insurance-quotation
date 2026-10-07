import { KeyRound, Palette, UserPlus } from "lucide-react";
import Link from "next/link";
import { getTranslations } from "next-intl/server";

import { Seal } from "@/components/brand/seal";
import type { Me } from "@/lib/me";
import { serverApi } from "@/lib/server/api";

export default async function HomePage() {
  const t = await getTranslations("home");
  const me = await serverApi<Me>("/api/v1/me");
  const firstName = (me.name || me.email).split(" ")[0];
  const steps = [
    { href: "/settings/branding", label: t("branding"), icon: Palette, show: me.permissions.includes("org:read") },
    { href: "/settings/members", label: t("team"), icon: UserPlus, show: me.permissions.includes("member:read") },
    { href: "/settings/security", label: t("security"), icon: KeyRound, show: !me.mfa_enrolled },
  ].filter((s) => s.show);

  return (
    <div className="grid gap-8">
      <div className="flex items-center gap-5">
        <Seal name={me.tenant.name} size={88} className="hidden text-primary sm:block" />
        <div>
          <h1 className="text-3xl sm:text-4xl">{t("greeting", { name: firstName ?? "" })}</h1>
          <p className="mt-2 max-w-prose text-lg text-muted-foreground">{t("body")}</p>
        </div>
      </div>
      <ul className="grid gap-2 sm:max-w-md">
        {steps.map(({ href, label, icon: Icon }) => (
          <li key={href}>
            <Link href={href} className="flex items-center gap-3 rounded-md border bg-card px-4 py-3 font-bold hover:border-primary">
              <Icon className="size-5 text-primary" aria-hidden="true" />
              {label}
            </Link>
          </li>
        ))}
      </ul>
    </div>
  );
}
