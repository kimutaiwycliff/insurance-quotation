import { Building2, CreditCard, Hash, KeyRound, Landmark, Package, Palette, Receipt, Smartphone, Users, type LucideIcon } from "lucide-react";

export interface SettingsSection {
  href: string;
  key: "organization" | "plan" | "members" | "insurers" | "items" | "payments" | "tax" | "numbering" | "branding" | "security";
  icon: LucideIcon;
  /** Shown only to members with this permission (security is personal, so always shown). */
  permission?: string;
  /** Shown only when the plan includes this feature. */
  feature?: string;
}

export const SETTINGS_SECTIONS: SettingsSection[] = [
  { href: "/settings/organization", key: "organization", icon: Building2, permission: "org:read" },
  { href: "/settings/plan", key: "plan", icon: CreditCard, permission: "org:read" },
  { href: "/settings/members", key: "members", icon: Users, permission: "member:read" },
  { href: "/settings/insurers", key: "insurers", icon: Landmark, permission: "insurer:read", feature: "insurance" },
  { href: "/settings/items", key: "items", icon: Package, permission: "invoice:write" },
  { href: "/settings/payments", key: "payments", icon: Smartphone, permission: "org:read" },
  { href: "/settings/tax", key: "tax", icon: Receipt, permission: "org:read" },
  { href: "/settings/branding", key: "branding", icon: Palette, permission: "org:read" },
  { href: "/settings/numbering", key: "numbering", icon: Hash, permission: "numbering:read" },
  { href: "/settings/security", key: "security", icon: KeyRound },
];

export function visibleSections(permissions: readonly string[], features: readonly string[]): SettingsSection[] {
  return SETTINGS_SECTIONS.filter(
    (s) => (!s.permission || permissions.includes(s.permission)) && (!s.feature || features.includes(s.feature) || features.includes("*")),
  );
}
