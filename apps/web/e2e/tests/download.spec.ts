import { expect, test } from "@playwright/test";

import { expectAccessible } from "./helpers";

test("anyone can open the Android download page without signing in", async ({ page }) => {
  await page.goto("/sign-in");
  await page.getByRole("link", { name: "Get the Android app" }).click();
  await expect(page).toHaveURL(/\/download$/);
  await expect(page.getByRole("heading", { name: "Get the Android app" })).toBeVisible();
  // No APK is published in the test stack, so the page says so instead of offering a broken link.
  await expect(page.getByRole("status")).toContainText("coming soon");
  await expectAccessible(page, "download");
});
