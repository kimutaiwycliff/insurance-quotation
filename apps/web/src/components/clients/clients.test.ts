import { describe, expect, it } from "vitest";

import { fromClient, toPayload, toUpdate } from "@/components/clients/client-form";
import { bucketOf } from "@/components/tasks/task-list";
import { formatPhone, whatsappLink } from "@/lib/format";

const base = {
  kind: "individual" as const,
  first_name: "Wanjiku",
  last_name: "Kamau",
  preferred_channel: "whatsapp" as const,
  marketing_consent: false,
  allow_duplicate: false,
};

describe("client payloads", () => {
  it("drops empty optional fields and splits tags", () => {
    expect(toPayload({ ...base, phone: "0712 345 678", email: "", tags: "vip, motor ,", town: "Nakuru" })).toMatchObject({
      first_name: "Wanjiku",
      phone: "0712 345 678",
      email: undefined,
      tags: ["vip", "motor"],
      address: { town: "Nakuru" },
    });
  });

  it("sends only changed fields, never an untouched ID number", () => {
    const update = toUpdate({ ...base, last_name: "Njeri", tags: "", id_number: "" }, { last_name: true, tags: true, id_number: true });
    expect(update).toEqual({ last_name: "Njeri", tags: [] });
  });

  it("round-trips an API client into form values", () => {
    const values = fromClient({
      id: "c1", kind: "individual", display_name: "Wanjiku Kamau", first_name: "Wanjiku", last_name: "Kamau",
      other_names: null, company_name: null, email: null, phone: "+254712345678", alt_phone: null,
      preferred_channel: "call", kra_pin: null, id_type: null, id_number_hint: "•••••678", date_of_birth: null,
      gender: null, occupation: null, address: { town: "Thika" }, source: null, referred_by_id: null, tags: ["vip"],
      owner_user_id: "u1", household_id: null, household_role: null, marketing_consent: true,
      marketing_consent_at: null, notes: null, status: "active", archived_at: null, created_at: "2026-10-01T00:00:00Z",
      updated_at: "2026-10-01T00:00:00Z", version: 1,
    });
    expect(values).toMatchObject({ town: "Thika", tags: "vip", preferred_channel: "call", id_number: "" });
  });
});

describe("tasks", () => {
  const now = new Date(2026, 9, 8, 12, 0, 0);
  it.each([
    [null, "none"],
    [new Date(2026, 9, 7, 18).toISOString(), "overdue"],
    [new Date(2026, 9, 8, 23).toISOString(), "today"],
    [new Date(2026, 9, 9, 0, 30).toISOString(), "upcoming"],
  ])("bucket of %s is %s", (due, expected) => {
    expect(bucketOf({ due_at: due }, now)).toBe(expected);
  });
});

describe("phones", () => {
  it("formats Kenyan numbers the local way", () => {
    expect(formatPhone("+254712345678")).toBe("0712 345 678");
    expect(formatPhone("+256772123456")).toBe("+256772123456");
    expect(formatPhone(null)).toBeNull();
    expect(whatsappLink("+254712345678")).toBe("https://wa.me/254712345678");
  });
});
