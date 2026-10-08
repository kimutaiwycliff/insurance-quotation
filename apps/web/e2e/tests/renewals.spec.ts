import { expect, test } from "@playwright/test";

import { expectAccessible, newAgency } from "./helpers";

function isoDate(offsetDays: number): string {
  const d = new Date();
  d.setDate(d.getDate() + offsetDays);
  return d.toISOString().slice(0, 10);
}

test("an agent enters an existing policy and works its renewal", async ({ page }, testInfo) => {
  await newAgency(page, `renewal-${testInfo.project.name}`);
  const mobile = testInfo.project.name === "mobile";

  await page.goto("/clients");
  await page.getByRole("button", { name: "Add client" }).click();
  const form = page.getByRole("dialog");
  await form.getByLabel("First name").fill("Achieng");
  await form.getByLabel("Last name").fill("Odhiambo");
  await form.getByLabel("Phone").fill(`07${Math.floor(10_000_000 + Math.random() * 89_999_999)}`);
  await form.getByRole("button", { name: "Save client" }).click();

  // Her motor cover, written last year with another insurer, ends in 10 days.
  await page.getByRole("link", { name: "Add policy" }).click();
  await page.getByLabel("Insurer", { exact: true }).fill("Jubilee Allianz");
  await page.getByLabel("What is covered").fill("KCB 789C Honda Fit");
  await page.getByLabel("Total premium (KES)").fill("38,500");
  await page.getByLabel("Cover starts").fill(isoDate(-355));
  await page.getByLabel("Cover ends").fill(isoDate(10));
  await page.getByLabel("The premium has been paid").check();
  await page.getByLabel("Paid on").fill(isoDate(-355));
  await page.getByLabel(/The insurer has confirmed cover/).check();
  await page.getByRole("button", { name: "Save policy" }).click();
  await expect(page.getByRole("heading", { name: "KCB 789C Honda Fit" })).toBeVisible();
  await expect(page.getByText("Active", { exact: true })).toBeVisible();
  await expect(page.getByText("in 10 days")).toBeVisible();
  await expectAccessible(page, "policy");

  // It shows on the renewal board, ready to contact on WhatsApp.
  await page.goto("/renewals");
  const due = page.getByRole("region", { name: /To contact/ });
  await expect(due.getByText("KCB 789C Honda Fit")).toBeVisible();
  await expect(due.getByRole("link", { name: "WhatsApp" })).toHaveAttribute("href", /^https:\/\/wa\.me\/254\d{9}\?text=Hello%20Achieng/);
  await expect(due.getByRole("link", { name: "Quote renewal" })).toBeVisible();
  await expectAccessible(page, "renewals");

  // She sold the car: the renewal is lost, with the reason.
  await due.getByRole("button", { name: "Lost" }).click();
  await page.getByLabel("Reason").fill("Sold the car");
  await page.getByRole("button", { name: "Mark as lost" }).click();
  if (mobile) await page.getByRole("tab", { name: /Lost/ }).click();
  const lost = page.getByRole("region", { name: /Lost/ });
  await expect(lost.getByText("Sold the car")).toBeVisible();
  await expect(lost.getByRole("button", { name: "Reopen" })).toBeVisible();
});
