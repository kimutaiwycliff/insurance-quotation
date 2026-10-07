import { redirect } from "next/navigation";
import type { ReactNode } from "react";

import { AppShell } from "@/components/shell/app-shell";
import type { Me } from "@/lib/me";
import { ApiError } from "@/lib/problem";
import { serverApi } from "@/lib/server/api";
import { getSession } from "@/lib/server/session";

export default async function AppLayout({ children }: { children: ReactNode }) {
  const session = await getSession();
  if (!session) redirect("/sign-in");
  if (!session.session.activeOrganizationId) redirect("/onboarding");
  let me: Me;
  try {
    me = await serverApi<Me>("/api/v1/me");
  } catch (error) {
    if (error instanceof ApiError && ["no_active_organization", "membership_inactive"].includes(error.code)) {
      redirect("/onboarding");
    }
    if (error instanceof ApiError && error.status === 401) redirect("/sign-in");
    throw error;
  }
  return <AppShell me={me}>{children}</AppShell>;
}
