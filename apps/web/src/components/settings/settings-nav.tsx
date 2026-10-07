"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useTranslations } from "next-intl";

import { SETTINGS_SECTIONS } from "@/components/settings/sections";
import { useMe } from "@/components/shell/me-context";
import { cn } from "@/lib/utils";

export function SettingsNav() {
  const t = useTranslations("settings");
  const pathname = usePathname();
  const me = useMe();
  const sections = SETTINGS_SECTIONS.filter((s) => !s.permission || (me.permissions as string[]).includes(s.permission));
  return (
    <nav aria-label={t("title")} className="-mx-4 overflow-x-auto px-4 md:mx-0 md:px-0">
      <ul className="flex gap-1 md:grid">
        {sections.map(({ href, key, icon: Icon }) => {
          const active = pathname === href;
          return (
            <li key={key}>
              <Link
                href={href}
                aria-current={active ? "page" : undefined}
                className={cn(
                  "flex items-center gap-2 rounded-md px-3 py-2 whitespace-nowrap hover:bg-accent",
                  active && "bg-accent font-bold",
                )}
              >
                <Icon className="size-4" aria-hidden="true" />
                {t(key)}
              </Link>
            </li>
          );
        })}
      </ul>
    </nav>
  );
}
