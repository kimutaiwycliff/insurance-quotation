import { expect, test } from "@playwright/test";

import { expectAccessible, newAgency } from "./helpers";

// A 1×1 PNG: enough to stand in for a logo.
const PNG = Buffer.from("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg==", "base64");

test("an owner picks a design, makes it theirs, and can remove the logo", async ({ page }, testInfo) => {
  test.setTimeout(150_000);
  await newAgency(page, `designs-${testInfo.project.name}`);
  await page.getByLabel("KRA PIN").fill("P051234567X");
  await page.getByRole("button", { name: "Continue" }).click();
  await expect(page.getByRole("heading", { name: "Your brand" })).toBeVisible();

  // Twelve designs, each with a live thumbnail.
  const gallery = page.getByRole("radiogroup", { name: "Design" });
  await expect(gallery.getByRole("radio")).toHaveCount(12);
  await gallery.getByRole("radio", { name: /Statement/ }).click();
  await expect(gallery.getByRole("radio", { name: /Statement/ })).toHaveAttribute("aria-checked", "true");

  // Make it theirs: a colour preset, a font, the signature lines.
  await page.getByRole("radio", { name: "Wine and gold" }).click();
  await expect(page.getByLabel("Main colour", { exact: true })).toHaveValue("#6B1D2A");
  await page.getByRole("radio", { name: /Editorial/ }).click();
  await page.getByRole("switch", { name: /Signature and stamp lines/ }).click();
  const preview = page.frameLocator("iframe[title^='Preview of a']");
  await expect(preview.getByText("Authorised signature")).toBeVisible();

  // A logo, then no logo: the agency name stands in.
  await page.locator('input[type="file"]').setInputFiles({ name: "logo.png", mimeType: "image/png", buffer: PNG });
  await expect(page.getByRole("button", { name: "Remove logo" })).toBeVisible();
  await expect(preview.locator("img.logo")).toHaveCount(1);
  await page.getByRole("button", { name: "Remove logo" }).click();
  await expect(page.getByText(/No logo: your agency name is shown instead/)).toBeVisible();
  await expect(preview.locator("img.logo")).toHaveCount(0);
  await page.screenshot({ path: testInfo.outputPath("designs.png"), fullPage: true });
  await expectAccessible(page, "designs");

  await page.getByRole("button", { name: "Finish setup" }).click();
  await expect(page.getByRole("heading", { name: /Welcome,/ })).toBeVisible();
  await page.goto("/settings/branding");
  await expect(page.getByRole("radiogroup", { name: "Design" }).getByRole("radio", { name: /Statement/ })).toHaveAttribute("aria-checked", "true");
  await expect(page.getByRole("switch", { name: /Signature and stamp lines/ })).toHaveAttribute("aria-checked", "true");
  await expect(page.getByRole("button", { name: "Remove logo" })).toHaveCount(0);
});
