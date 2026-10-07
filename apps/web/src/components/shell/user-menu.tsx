"use client";

import { Check, LogOut, Monitor, Moon, Shield, Sun } from "lucide-react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useTranslations } from "next-intl";
import { useTheme } from "next-themes";

import { Seal } from "@/components/brand/seal";
import { Button } from "@/components/ui/button";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuRadioGroup,
  DropdownMenuRadioItem,
  DropdownMenuSeparator,
  DropdownMenuSub,
  DropdownMenuSubContent,
  DropdownMenuSubTrigger,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { authClient, bumpOrgEpoch } from "@/lib/auth-client";
import type { Me } from "@/lib/me";

export function UserMenu({ me }: { me: Me }) {
  const t = useTranslations("nav");
  const common = useTranslations("common");
  const router = useRouter();
  const { theme, setTheme } = useTheme();
  const orgs = authClient.useListOrganizations();
  const active = authClient.useActiveOrganization();

  async function switchTo(organizationId: string) {
    await authClient.organization.setActive({ organizationId });
    bumpOrgEpoch();
    router.refresh();
  }

  async function signOut() {
    await authClient.signOut();
    router.replace("/sign-in");
    router.refresh();
  }

  return (
    <DropdownMenu>
      <DropdownMenuTrigger asChild>
        <Button variant="ghost" className="gap-2 px-2" aria-label={`${me.name || me.email}, ${me.tenant.name}`}>
          <span aria-hidden="true" className="grid size-8 place-items-center rounded-full bg-primary font-bold text-primary-foreground">
            {(me.name || me.email).slice(0, 1).toUpperCase()}
          </span>
        </Button>
      </DropdownMenuTrigger>
      <DropdownMenuContent align="end" className="w-64">
        <DropdownMenuLabel className="grid">
          <span className="font-bold">{me.name || me.email}</span>
          <span className="text-sm font-normal text-muted-foreground">{me.email}</span>
        </DropdownMenuLabel>
        <DropdownMenuSeparator />
        {(orgs.data?.length ?? 0) > 1 && (
          <DropdownMenuSub>
            <DropdownMenuSubTrigger>{t("switchAgency")}</DropdownMenuSubTrigger>
            <DropdownMenuSubContent>
              {orgs.data?.map((org) => (
                <DropdownMenuItem key={org.id} onSelect={() => switchTo(org.id)}>
                  <Seal name={org.name} size={22} className="text-primary" />
                  {org.name}
                  {active.data?.id === org.id && <Check className="ml-auto" aria-label="Current" />}
                </DropdownMenuItem>
              ))}
            </DropdownMenuSubContent>
          </DropdownMenuSub>
        )}
        <DropdownMenuItem asChild>
          <Link href="/settings/security">
            <Shield aria-hidden="true" /> Security
          </Link>
        </DropdownMenuItem>
        <DropdownMenuSub>
          <DropdownMenuSubTrigger>{t("theme")}</DropdownMenuSubTrigger>
          <DropdownMenuSubContent>
            <DropdownMenuRadioGroup value={theme} onValueChange={setTheme}>
              <DropdownMenuRadioItem value="light"><Sun aria-hidden="true" /> Light</DropdownMenuRadioItem>
              <DropdownMenuRadioItem value="dark"><Moon aria-hidden="true" /> Dark</DropdownMenuRadioItem>
              <DropdownMenuRadioItem value="system"><Monitor aria-hidden="true" /> Device setting</DropdownMenuRadioItem>
            </DropdownMenuRadioGroup>
          </DropdownMenuSubContent>
        </DropdownMenuSub>
        <DropdownMenuSeparator />
        <DropdownMenuItem onSelect={signOut}>
          <LogOut aria-hidden="true" /> {common("signOut")}
        </DropdownMenuItem>
      </DropdownMenuContent>
    </DropdownMenu>
  );
}
