"use client";

import { createContext, useContext, type ReactNode } from "react";

import type { Me } from "@/lib/me";

const MeContext = createContext<Me | null>(null);

export function MeProvider({ me, children }: { me: Me; children: ReactNode }) {
  return <MeContext.Provider value={me}>{children}</MeContext.Provider>;
}

/** The signed-in member in the active agency (resolved server-side by the app layout). */
export function useMe(): Me {
  const me = useContext(MeContext);
  if (!me) throw new Error("useMe must be used inside the app shell");
  return me;
}

export function useCan(permission: string): boolean {
  return (useMe().permissions as string[]).includes(permission);
}
