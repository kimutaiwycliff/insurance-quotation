import { Lock } from "lucide-react";
import Link from "next/link";
import type { ReactNode } from "react";

import { hasFeature } from "@/components/shell/nav";
import type { Me } from "@/lib/me";
import { serverApi } from "@/lib/server/api";

const NAMES: Record<string, string> = {
  insurance: "Quotes, policies and renewals",
  commission: "Commission tracking",
};

/** Route-level gate: pages outside the plan show what unlocks them instead of failing with 402. */
export async function PlanGate({ feature, children }: { feature: string; children: ReactNode }) {
  const me = await serverApi<Me>("/api/v1/me");
  if (hasFeature(me.features, feature)) return children;
  return (
    <section className="mx-auto grid max-w-md justify-items-center gap-4 py-16 text-center">
      <Lock className="size-8 text-muted-foreground" aria-hidden="true" />
      <h1 className="text-2xl">{NAMES[feature] ?? "This page"} is not in your plan</h1>
      <p className="text-muted-foreground">Your data is safe. Change your plan to use this again.</p>
      <Link href="/settings/plan" className="font-bold underline underline-offset-2">See plans</Link>
    </section>
  );
}
