import { describe, expect, it } from "vitest";

import { initials } from "@/components/brand/seal";
import { slugify } from "@/components/onboarding/wizard";
import { changedFields } from "@/components/settings/organization-form";
import { formatMoney, relativeTime, sumAmounts } from "@/lib/format";
import { safeNext } from "@/lib/navigation";
import { fieldErrors, parseProblem, problemMessage } from "@/lib/problem";

describe("problem+json mapping", () => {
  it("maps field errors to form field names", () => {
    expect(
      fieldErrors({
        status: 422,
        code: "validation_error",
        title: "Request validation failed",
        errors: [
          { field: "body.tax_pin", message: "Bad PIN", code: "x" },
          { field: "body.tax_pin", message: "second", code: "y" },
          { field: "body.address.city", message: "Required", code: "z" },
        ],
      }),
    ).toEqual({ tax_pin: "Bad PIN", "address.city": "Required" });
  });

  it("explains conflicts in plain words", () => {
    expect(problemMessage({ status: 412, code: "version_conflict", title: "x" })).toMatch(/Reload/);
    expect(problemMessage({ status: 400, code: "other", title: "Title", detail: "Detail" })).toBe("Detail");
  });

  it("parses non-JSON failures", async () => {
    const problem = await parseProblem(new Response("<html>", { status: 502, statusText: "Bad Gateway" }));
    expect(problem).toMatchObject({ status: 502, code: "http_error", title: "Bad Gateway" });
  });
});

describe("formatting", () => {
  it("formats money from strings without floats", () => {
    expect(formatMoney("1234567.5", "KES")).toBe("KES 1,234,567.50");
    expect(formatMoney("1850000", "UGX")).toBe("UGX 1,850,000");
    expect(formatMoney("-12.345", "KWD")).toBe("-KWD 12.345");
    expect(formatMoney("90071992547409931.10", "KES")).toBe("KES 90,071,992,547,409,931.10");
  });

  it("formats relative times", () => {
    const now = new Date("2026-10-07T12:00:00Z");
    expect(relativeTime("2026-10-07T11:00:00Z", now)).toBe("1 hour ago");
    expect(relativeTime("2026-10-06T12:00:00Z", now)).toBe("yesterday");
  });
});

describe("navigation", () => {
  it.each([
    ["/settings", "/settings"],
    ["https://evil.example", "/"],
    ["//evil.example", "/"],
    ["/\\evil.example", "/"],
    [null, "/"],
  ])("safeNext(%s) = %s", (input, expected) => {
    expect(safeNext(input)).toBe(expected);
  });
});

describe("agency helpers", () => {
  it("builds seal initials", () => {
    expect(initials("Wanjiku Insurance Agency")).toBe("WI");
    expect(initials("The Otieno & Sons Agency Ltd")).toBe("OS");
    expect(initials("Jubilee")).toBe("JU");
  });

  it("slugifies names", () => {
    expect(slugify("Wanjiku Insurance Agency")).toMatch(/^wanjiku-insurance-agency-[a-z0-9]{1,4}$/);
    expect(slugify("!!!")).toMatch(/^agency-/);
  });

  it("sends only changed organization fields, clearing emptied ones", () => {
    const values = {
      name: "Wanjiku Agency",
      legal_name: "",
      tax_pin: "p051234567x",
      intermediary_type: "agent" as const,
      default_currency: "KES",
      timezone: "Africa/Nairobi",
      fiscal_year_start_month: "1",
    };
    expect(changedFields(values, { name: true, legal_name: true, tax_pin: true })).toEqual({
      name: "Wanjiku Agency",
      legal_name: null,
      tax_pin: "P051234567X",
    });
  });
});

describe("randomId", () => {
  it("makes RFC 4122 v4 ids without crypto.randomUUID", async () => {
    const { randomId } = await import("@/lib/utils");
    const id = randomId();
    expect(id).toMatch(/^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/);
    expect(new Set(Array.from({ length: 100 }, randomId)).size).toBe(100);
  });
});

describe("percent strings", () => {
  it.each([
    ["4", "0.04"],
    ["0.25", "0.0025"],
    ["3.5", "0.035"],
    ["10", "0.1"],
    ["100", "1"],
    ["0", "0"],
    ["12.345678", "0.12345678"],
  ])("%s%% → %s", async (percent, fraction) => {
    const { percentToFraction, fractionToPercent } = await import("@/lib/format");
    expect(percentToFraction(percent)).toBe(fraction);
    expect(fractionToPercent(fraction)).toBe(percent);
  });

  it("rejects junk", async () => {
    const { percentToFraction } = await import("@/lib/format");
    for (const bad of ["", "abc", "-1", "1e2", "4%"]) expect(percentToFraction(bad)).toBeNull();
  });
});

describe("sumAmounts", () => {
  it("adds money strings exactly", () => {
    expect(sumAmounts(["0.10", "0.20"])).toBe("0.30");
    expect(sumAmounts(["3500", "4000.5", "", "abc"])).toBe("7500.50");
    expect(sumAmounts(["-10.25", "5"])).toBe("-5.25");
    expect(sumAmounts([])).toBe("0.00");
  });
});
