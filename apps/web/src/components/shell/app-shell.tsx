"use client";

import { Menu } from "lucide-react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { useTranslations } from "next-intl";
import { useState, type ReactNode } from "react";

import { Seal } from "@/components/brand/seal";
import { CommandMenu } from "@/components/shell/command-menu";
import { MeProvider, useMe } from "@/components/shell/me-context";
import { isActive, visibleNav } from "@/components/shell/nav";
import { NotificationBell } from "@/components/shell/notification-bell";
import { PlanBanner } from "@/components/shell/plan-banner";
import { UserMenu } from "@/components/shell/user-menu";
import { Button } from "@/components/ui/button";
import { Sheet, SheetContent, SheetTitle, SheetTrigger } from "@/components/ui/sheet";
import type { Me } from "@/lib/me";
import { cn } from "@/lib/utils";

function NavLinks({ onNavigate }: { onNavigate?: () => void }) {
  const t = useTranslations("nav");
  const pathname = usePathname();
  const me = useMe();
  return (
    <nav aria-label="Main" className="grid gap-0.5">
      {visibleNav(me.permissions as string[], me.features).map(({ href, key, icon: Icon, soon }) => {
        const active = isActive(pathname, href);
        if (soon) {
          return (
            <span
              key={key}
              aria-disabled="true"
              className="flex items-center gap-3 rounded-md px-3 py-2 text-muted-foreground/70"
            >
              <Icon className="size-5" aria-hidden="true" />
              <span>{t(key)}</span>
              <span className="ml-auto text-xs">{t("soon")}</span>
            </span>
          );
        }
        return (
          <Link
            key={key}
            href={href}
            onClick={onNavigate}
            aria-current={active ? "page" : undefined}
            className={cn(
              "relative flex items-center gap-3 rounded-md px-3 py-2 font-bold transition-colors hover:bg-accent",
              active && "bg-accent text-foreground",
            )}
          >
            {active && <span aria-hidden="true" className="absolute inset-y-1.5 left-0 w-1 rounded-full bg-maize" />}
            <Icon className="size-5" aria-hidden="true" />
            {t(key)}
          </Link>
        );
      })}
    </nav>
  );
}

function AgencyMark({ me }: { me: Me }) {
  return (
    <Link href="/" className="flex items-center gap-3 rounded-md px-1 py-1">
      <Seal name={me.tenant.name} size={40} className="text-primary" />
      <span className="font-heading leading-tight font-bold">{me.tenant.name}</span>
    </Link>
  );
}

export function AppShell({ me, children }: { me: Me; children: ReactNode }) {
  const t = useTranslations("nav");
  const [open, setOpen] = useState(false);
  return (
    <MeProvider me={me}>
    <div className="min-h-dvh lg:grid lg:grid-cols-[17rem_minmax(0,1fr)]">
      <aside className="sticky top-0 hidden h-dvh flex-col gap-6 border-r bg-card px-4 py-5 lg:flex">
        <AgencyMark me={me} />
        <NavLinks />
      </aside>
      <div className="flex min-w-0 flex-col">
        <header className="sticky top-0 z-30 flex items-center gap-2 border-b bg-background/95 px-4 py-2.5 backdrop-blur sm:px-6">
          <Sheet open={open} onOpenChange={setOpen}>
            <SheetTrigger asChild>
              <Button variant="ghost" size="icon" className="lg:hidden" aria-label={t("menu")}>
                <Menu className="size-5" />
              </Button>
            </SheetTrigger>
            <SheetContent side="left" className="w-72 gap-6 p-4">
              <SheetTitle className="sr-only">{t("menu")}</SheetTitle>
              <AgencyMark me={me} />
              <NavLinks onNavigate={() => setOpen(false)} />
            </SheetContent>
          </Sheet>
          <CommandMenu me={me} />
          <div className="ml-auto flex items-center gap-1">
            <NotificationBell />
            <UserMenu me={me} />
          </div>
        </header>
        <PlanBanner />
        <main id="main" className="mx-auto w-full max-w-5xl flex-1 px-4 py-6 sm:px-6 sm:py-8">
          {children}
        </main>
      </div>
    </div>
    </MeProvider>
  );
}
