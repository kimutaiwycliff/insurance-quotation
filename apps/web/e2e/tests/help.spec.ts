import { expect, test } from "@playwright/test";

import { expectAccessible, newAgency } from "./helpers";

test("an agent finds their way with the in-app guide", async ({ page }, testInfo) => {
  await newAgency(page, `help-${testInfo.project.name}`);
  const mobile = testInfo.project.name === "mobile";

  // The guide is in the main menu.
  if (mobile) {
    await page.getByRole("button", { name: "Open menu" }).click();
    await page.getByRole("dialog").getByRole("link", { name: "Help & guide" }).click();
  } else {
    await page.getByRole("navigation", { name: "Main" }).getByRole("link", { name: "Help & guide" }).click();
  }
  await expect(page.getByRole("heading", { name: "Help & guide", level: 1 })).toBeVisible();

  // The setup card stamps what is already done: onboarding filled in the KRA PIN.
  const card = page.getByRole("region", { name: "Your first week" });
  await expect(card.getByRole("link", { name: /Add your KRA PIN and licence \(done\)/ })).toBeVisible();
  await expect(card.getByRole("link", { name: /Add your first client \(to do\)/ })).toBeVisible();
  await page.screenshot({ path: testInfo.outputPath("help-home.png"), fullPage: true });
  await expectAccessible(page, "help");

  // Search: M-Pesa spelled any way, with the matching words marked.
  await page.keyboard.press("/");
  await expect(page.getByLabel("Search the guide")).toBeFocused();
  await page.keyboard.type("m pesa prompt");
  await expect(page.getByRole("status").filter({ hasText: /match/ })).toBeVisible();
  const topic = page.getByRole("button", { name: /Send an M-Pesa prompt/ });
  await topic.click();
  await expect(topic).toHaveAttribute("aria-expanded", "true");
  await expect(page.getByRole("region", { name: /Send an M-Pesa prompt/ }).getByText("Wait for the confirmation.")).toBeVisible();
  await page.screenshot({ path: testInfo.outputPath("help-search.png"), fullPage: true });
  await expectAccessible(page, "help search");

  // Nothing found: suggestions instead of a dead end.
  await page.getByLabel("Search the guide").fill("zebra crossing");
  await expect(page.getByText("Nothing matches “zebra crossing” yet.")).toBeVisible();
  await page.getByRole("button", { name: "renewals" }).first().click();
  await expect(page.getByRole("button", { name: /Never miss a renewal/ })).toBeVisible();

  // Areas filter the list, and "Take me there" goes to the page.
  await page.getByRole("button", { name: "Clear search" }).click();
  await page.getByRole("radio", { name: /Invoices & getting paid/ }).click();
  await expect(page.getByRole("heading", { name: "Invoices & getting paid", level: 3 })).toBeVisible();
  await expect(page.getByRole("heading", { name: "Clients & leads", level: 3 })).toHaveCount(0);
  await page.getByRole("button", { name: /Get paid by M-Pesa/ }).click();
  await page.getByRole("link", { name: "Open Payments settings" }).click();
  await expect(page).toHaveURL(/\/settings\/payments$/);

  // A shared link opens the topic directly.
  await page.goto("/help#topic-invoice");
  await expect(page.getByRole("button", { name: /Send an invoice/ })).toHaveAttribute("aria-expanded", "true");
});
