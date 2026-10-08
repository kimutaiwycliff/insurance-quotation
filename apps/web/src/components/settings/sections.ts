import { Building2, Hash, KeyRound, Landmark, Palette, Users, type LucideIcon } from "lucide-react";

export interface SettingsSection {
  href: string;
  key: "organization" | "members" | "insurers" | "numbering" | "branding" | "security";
  icon: LucideIcon;
  /** Shown only to members with this permission (security is personal, so always shown). */
  permission?: string;
}

export const SETTINGS_SECTIONS: SettingsSection[] = [
  { href: "/settings/organization", key: "organization", icon: Building2, permission: "org:read" },
  { href: "/settings/members", key: "members", icon: Users, permission: "member:read" },
  { href: "/settings/insurers", key: "insurers", icon: Landmark, permission: "insurer:read" },
  { href: "/settings/branding", key: "branding", icon: Palette, permission: "org:read" },
  { href: "/settings/numbering", key: "numbering", icon: Hash, permission: "numbering:read" },
  { href: "/settings/security", key: "security", icon: KeyRound },
];
