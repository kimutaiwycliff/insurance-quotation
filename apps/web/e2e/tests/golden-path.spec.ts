import { expect, test } from "@playwright/test";

import { expectAccessible, mailLink, uniqueEmail } from "./helpers";

/**
 * W1 acceptance: sign up → confirm email → create agency → details → branding → home, on desktop and a 390 px
 * phone, with axe checks along the way.
 */
test("an agent sets up their agency from scratch", async ({ page }, testInfo) => {
  const email = uniqueEmail(testInfo.project.name);
  const agency = `Wanjiku ${testInfo.project.name === "mobile" ? "Mobile" : "Desktop"} Insurance Agency`;

  await page.goto("/");
  await expect(page).toHaveURL(/\/sign-in/);
  await expectAccessible(page, "sign-in");

  await page.getByRole("link", { name: "Create an account" }).click();
  await page.getByLabel("Your name").fill("Wanjiku Kamau");
  await page.getByLabel("Email").fill(email);
  await page.getByLabel("Password").fill("correct-horse-battery-9");
  await expectAccessible(page, "sign-up");
  await page.screenshot({ path: testInfo.outputPath("01-sign-up.png"), fullPage: true });
  await page.getByRole("button", { name: "Create account" }).click();
  await expect(page.getByRole("heading", { name: "Check your email" })).toBeVisible();

  const link = await mailLink(page, email, "/api/auth/verify-email");
  await page.goto(link);
  await expect(page.getByRole("heading", { name: "Email confirmed" })).toBeVisible();
  await page.getByRole("link", { name: "Set up my agency" }).click();

  // Step 1: the agency (organization). The stamp seal follows the name being typed.
  await expect(page).toHaveURL(/\/onboarding/);
  await page.getByLabel("Agency name").fill(agency);
  await expectAccessible(page, "onboarding: agency");
  await page.screenshot({ path: testInfo.outputPath("02-onboarding-agency.png"), fullPage: true });
  await page.getByRole("button", { name: "Create agency" }).click();

  // Step 2: details shown on documents.
  await expect(page.getByRole("heading", { name: "Agency details" })).toBeVisible();
  await page.getByLabel("KRA PIN").fill("p051234567x");
  await page.getByLabel("Office phone").fill("+254 712 345 678");
  await expectAccessible(page, "onboarding: details");
  await page.getByRole("button", { name: "Continue" }).click();

  // Step 3: brand, with a live preview of a real quotation.
  await expect(page.getByRole("heading", { name: "Your brand" })).toBeVisible();
  await page.getByRole("radio", { name: /Savanna/ }).click();
  await page.getByLabel("Main colour", { exact: true }).fill("#7A1F3D");
  const preview = page.frameLocator("iframe[title^='Preview of a']");
  await expect(preview.getByText(agency).first()).toBeVisible();
  await expect(page.locator("iframe[title^='Preview of a']")).toHaveAttribute("sandbox", "");
  await expectAccessible(page, "onboarding: brand");
  await page.screenshot({ path: testInfo.outputPath("03-onboarding-brand.png"), fullPage: true });
  await page.getByRole("button", { name: "Finish setup" }).click();

  // Home inside the app shell.
  await expect(page.getByRole("heading", { name: "Welcome, Wanjiku" })).toBeVisible();
  await expectAccessible(page, "home");
  await page.screenshot({ path: testInfo.outputPath("04-home.png"), fullPage: true });

  if (testInfo.project.name === "mobile") {
    await page.getByRole("button", { name: "Open menu" }).click();
    await page.getByRole("dialog").getByRole("link", { name: "Settings" }).click();
  } else {
    await page.getByRole("navigation", { name: "Main" }).getByRole("link", { name: "Settings" }).click();
  }
  await expect(page.getByLabel("Trading name")).toHaveValue(agency);
  await expect(page.getByLabel("KRA PIN")).toHaveValue("P051234567X");
  await expectAccessible(page, "settings: organization");
  await page.screenshot({ path: testInfo.outputPath("05-settings-organization.png"), fullPage: true });

  await page.goto("/settings/branding");
  await expect(page.getByRole("radio", { name: /Savanna/ })).toHaveAttribute("aria-checked", "true");
  await expect(page.getByLabel("Main colour", { exact: true })).toHaveValue("#7A1F3D");

  await page.goto("/settings/numbering");
  await expect(page.getByText(/QT-\d{4}-00001/)).toBeVisible();
  await expectAccessible(page, "settings: numbering");
});
