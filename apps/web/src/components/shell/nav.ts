import {
  Calculator,
  CalendarClock,
  FileText,
  Funnel,
  Home,
  ListChecks,
  type LucideIcon,
  Settings,
  ShieldCheck,
  Users,
  Wallet,
} from "lucide-react";

export interface NavItem {
  href: string;
  key:
    | "home"
    | "clients"
    | "leads"
    | "tasks"
    | "calculator"
    | "quotes"
    | "policies"
    | "renewals"
    | "commission"
    | "settings";
  icon: LucideIcon;
  /** Modules arriving in R1 are listed so agents see where the product is going, but disabled. */
  soon?: boolean;
  /** Shown only to members with at least one of these permissions. */
  anyOf?: string[];
}

export const NAV: NavItem[] = [
  { href: "/", key: "home", icon: Home },
  { href: "/clients", key: "clients", icon: Users },
  { href: "/leads", key: "leads", icon: Funnel },
  { href: "/tasks", key: "tasks", icon: ListChecks },
  { href: "/calculator", key: "calculator", icon: Calculator },
  { href: "/quotes", key: "quotes", icon: FileText },
  { href: "/policies", key: "policies", icon: ShieldCheck },
  { href: "/renewals", key: "renewals", icon: CalendarClock },
  { href: "/commission", key: "commission", icon: Wallet, anyOf: ["commission:read:own", "commission:read:all"] },
  { href: "/settings", key: "settings", icon: Settings },
];

export function visibleNav(permissions: readonly string[]): NavItem[] {
  return NAV.filter((item) => !item.anyOf || item.anyOf.some((p) => permissions.includes(p)));
}

export function isActive(pathname: string, href: string): boolean {
  return href === "/" ? pathname === "/" : pathname === href || pathname.startsWith(`${href}/`);
}
