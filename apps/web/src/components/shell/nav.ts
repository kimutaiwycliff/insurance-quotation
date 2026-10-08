import { CalendarClock, FileText, Funnel, Home, ListChecks, type LucideIcon, Settings, ShieldCheck, Users } from "lucide-react";

export interface NavItem {
  href: string;
  key: "home" | "clients" | "leads" | "tasks" | "quotes" | "policies" | "renewals" | "settings";
  icon: LucideIcon;
  /** Modules arriving in R1 are listed so agents see where the product is going, but disabled. */
  soon?: boolean;
}

export const NAV: NavItem[] = [
  { href: "/", key: "home", icon: Home },
  { href: "/clients", key: "clients", icon: Users },
  { href: "/leads", key: "leads", icon: Funnel },
  { href: "/tasks", key: "tasks", icon: ListChecks },
  { href: "/quotes", key: "quotes", icon: FileText, soon: true },
  { href: "/policies", key: "policies", icon: ShieldCheck, soon: true },
  { href: "/renewals", key: "renewals", icon: CalendarClock, soon: true },
  { href: "/settings", key: "settings", icon: Settings },
];

export function isActive(pathname: string, href: string): boolean {
  return href === "/" ? pathname === "/" : pathname === href || pathname.startsWith(`${href}/`);
}
