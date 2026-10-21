import { expect, test } from "@playwright/test";

import { expectAccessible } from "./helpers";

test("signed-out visitors see the landing page at / and can start a trial", async ({ page }) => {
  await page.goto("/");
  await expect(page).toHaveURL(/\/$/);
  await expect(page.getByRole("heading", { level: 1, name: "Never miss a renewal again." })).toBeVisible();
  // The hero story ends with the accepted quote turning into a policy.
  await expect(page.getByText("Policy created, renewal reminder set")).toBeVisible();
  await expectAccessible(page, "landing");

  // Yearly prices replace monthly ones.
  const pricing = page.locator("#pricing");
  await expect(pricing.getByText("KES 1,500")).toBeVisible();
  await pricing.getByRole("radio", { name: "Yearly, 2 months free" }).click();
  await expect(pricing.getByText("KES 15,000")).toBeVisible();

  // Questions open on demand.
  await page.getByText("Do I need a card to start?").click();
  await expect(page.getByText("Every new account gets 14 days of the Agency plan")).toBeVisible();

  await page.getByRole("main").getByRole("link", { name: "Start 14 days free" }).first().click();
  await expect(page).toHaveURL(/\/sign-up/);
});

test("signed-out visitors of app pages still go to sign-in", async ({ page }) => {
  await page.goto("/clients");
  await expect(page).toHaveURL(/\/sign-in\?next=%2Fclients/);
});
