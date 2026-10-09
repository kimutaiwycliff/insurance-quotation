import { expect, test } from "@playwright/test";

import { expectAccessible, newAgency } from "./helpers";

test("a new agency on the trial picks a plan and pays by M-Pesa", async ({ page }, testInfo) => {
  test.setTimeout(120_000);
  await newAgency(page, `plans-${testInfo.project.name}`);

  await page.goto("/settings/plan");
  await expect(page.getByText("Free trial", { exact: true })).toBeVisible();
  await expect(page.getByText(/You have every Agency feature until/)).toBeVisible();
  await expect(page.getByText(/Founding offer: half price/)).toBeVisible();
  const agent = page.getByRole("listitem").filter({ has: page.getByRole("heading", { name: "Agent" }) });
  await expect(agent.getByText("KES 750.00")).toBeVisible(); // founding price of KES 1,500
  await page.getByRole("radio", { name: "Yearly (2 months free)" }).click();
  await expect(agent.getByText("KES 7,500.00")).toBeVisible();
  await expectAccessible(page, "plans");

  await page.getByRole("radio", { name: "Monthly" }).click();
  await agent.getByRole("button", { name: "Choose Agent" }).click();
  const dialog = page.getByRole("dialog");
  await dialog.getByLabel("Your M-Pesa number").fill("0712 345 678");
  await dialog.getByRole("button", { name: /Send prompt for KES 750/ }).click();
  await expect(dialog.getByText(/Paid\. Thank you!/)).toBeVisible({ timeout: 30_000 });
  await dialog.getByRole("button", { name: "Done" }).click();

  await expect(page.getByText("Active", { exact: true })).toBeVisible();
  await expect(page.getByText(/Founding member: 50% off/)).toBeVisible();
  await expect(page.getByText(/Paid until/)).toBeVisible();
  await expect(page.getByRole("cell", { name: /^SIM/ })).toBeVisible(); // receipt in the history
});
