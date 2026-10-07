"use client";

import { Search } from "lucide-react";
import { useRouter } from "next/navigation";
import { useTranslations } from "next-intl";
import { useEffect, useState } from "react";

import { NAV } from "@/components/shell/nav";
import { SETTINGS_SECTIONS } from "@/components/settings/sections";
import {
  CommandDialog,
  CommandEmpty,
  CommandGroup,
  CommandInput,
  CommandItem,
  CommandList,
} from "@/components/ui/command";
import type { Me } from "@/lib/me";

/** ⌘K / Ctrl+K: jump anywhere. Records (clients, policies) join the search as their modules arrive. */
export function CommandMenu({ me }: { me: Me }) {
  const t = useTranslations("nav");
  const s = useTranslations("settings");
  const router = useRouter();
  const [open, setOpen] = useState(false);

  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      if (event.key.toLowerCase() === "k" && (event.metaKey || event.ctrlKey)) {
        event.preventDefault();
        setOpen((value) => !value);
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);

  const go = (href: string) => {
    setOpen(false);
    router.push(href);
  };

  return (
    <>
      <button
        type="button"
        onClick={() => setOpen(true)}
        className="flex h-10 min-w-0 flex-1 items-center gap-2 rounded-md border bg-card px-3 text-left text-muted-foreground hover:bg-accent sm:max-w-sm"
      >
        <Search className="size-4 shrink-0" aria-hidden="true" />
        <span className="truncate">{t("search")}</span>
        <kbd className="ml-auto hidden rounded border px-1.5 text-xs sm:inline">⌘K</kbd>
      </button>
      <CommandDialog open={open} onOpenChange={setOpen} title={t("search")} description={me.tenant.name}>
        <CommandInput placeholder={t("search")} />
        <CommandList>
          <CommandEmpty>No matches.</CommandEmpty>
          <CommandGroup heading={t("home")}>
            {NAV.filter((item) => !item.soon).map(({ href, key, icon: Icon }) => (
              <CommandItem key={key} onSelect={() => go(href)}>
                <Icon aria-hidden="true" /> {t(key)}
              </CommandItem>
            ))}
          </CommandGroup>
          <CommandGroup heading={s("title")}>
            {SETTINGS_SECTIONS.filter((x) => !x.permission || (me.permissions as string[]).includes(x.permission)).map(
              ({ href, key, icon: Icon }) => (
                <CommandItem key={key} onSelect={() => go(href)}>
                  <Icon aria-hidden="true" /> {s(key)}
                </CommandItem>
              ),
            )}
          </CommandGroup>
        </CommandList>
      </CommandDialog>
    </>
  );
}
