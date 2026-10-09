import { describe, expect, it } from "vitest";

import { visibleSections } from "@/components/settings/sections";
import { hasFeature, visibleNav } from "@/components/shell/nav";
import { daysUntil } from "@/lib/format";

const ALL = ["commission:read:all", "invoice:write", "org:read", "insurer:read"];

describe("plan features in navigation", () => {
  it("hides insurance and commission for the Business plan", () => {
    const keys = visibleNav(ALL, ["branding", "team"]).map((i) => i.key);
    expect(keys).toEqual(["home", "clients", "leads", "tasks", "invoices", "settings"]);
    expect(visibleSections(ALL, ["branding"]).map((s) => s.key)).not.toContain("insurers");
  });

  it("shows everything for the platform and with a full plan", () => {
    expect(hasFeature(["*"], "insurance")).toBe(true);
    expect(visibleNav(ALL, ["insurance", "commission"]).map((i) => i.key)).toContain("commission");
    expect(visibleSections(ALL, ["insurance"]).map((s) => s.key)).toContain("plan");
  });
});

describe("daysUntil", () => {
  const now = new Date("2026-10-09T09:00:00Z");
  it("rounds part days up and never goes negative", () => {
    expect(daysUntil("2026-10-16T08:00:00Z", now)).toBe(7);
    expect(daysUntil("2026-10-09T10:00:00Z", now)).toBe(1);
    expect(daysUntil("2026-10-01T00:00:00Z", now)).toBe(0);
  });
});
