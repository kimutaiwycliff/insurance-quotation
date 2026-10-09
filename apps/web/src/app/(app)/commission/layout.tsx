import type { ReactNode } from "react";

import { PlanGate } from "@/components/shell/plan-gate";

export default function Layout({ children }: { children: ReactNode }) {
  return <PlanGate feature="commission">{children}</PlanGate>;
}
