import { describe, expect, it } from "vitest";

import { AREAS, TOPICS, canSee, normalise, searchTopics } from "@/components/help/topics";

const ids = (q: string) => searchTopics(TOPICS, q).map((t) => t.id);

describe("guide search", () => {
  it("treats M-Pesa spellings alike", () => {
    expect(normalise("M-Pesa")).toBe("mpesa");
    expect(normalise("m pesa Paybill")).toBe("mpesa paybill");
    for (const q of ["mpesa", "M-Pesa", "m pesa"]) expect(ids(q)).toContain("mpesa-prompt");
  });

  it("ranks title matches first and needs every word", () => {
    expect(ids("renewal")[0]).toBe("renewals");
    expect(ids("whatsapp quote")).toContain("send-quote");
    expect(ids("whatsapp zebra")).toEqual([]);
  });

  it("understands everyday words", () => {
    expect(ids("bill")).toContain("invoice");
    expect(ids("excel")[0]).toBe("import");
    expect(ids("logo")[0]).toBe("brand");
  });

  it("matches the start of words as people type", () => {
    expect(ids("commis")).toContain("commission");
  });

  it("returns everything for an empty query", () => {
    expect(searchTopics(TOPICS, "  ")).toHaveLength(TOPICS.length);
  });
});

describe("what each member sees", () => {
  const all = ["client:read:all", "client:write", "insurer:read", "commission:read:all", "invoice:write", "org:read", "member:read"];

  it("hides insurance topics on the Business plan", () => {
    const seen = TOPICS.filter((t) => canSee(t, all, ["branding", "team"])).map((t) => t.id);
    expect(seen).not.toContain("send-quote");
    expect(seen).not.toContain("commission");
    expect(seen).toContain("invoice");
  });

  it("hides money topics from an assistant", () => {
    const seen = TOPICS.filter((t) => canSee(t, ["client:read:all", "client:write", "task:write"], ["*"])).map((t) => t.id);
    expect(seen).toContain("add-client");
    expect(seen).not.toContain("record-payment");
    expect(seen).not.toContain("commission");
  });

  it("files every topic under a known area, with unique ids", () => {
    const keys = new Set(AREAS.map((a) => a.key));
    expect(TOPICS.every((t) => keys.has(t.area))).toBe(true);
    expect(new Set(TOPICS.map((t) => t.id)).size).toBe(TOPICS.length);
  });
});
