import { expect, test } from "@playwright/test";

import { expectAccessible, newAgency } from "./helpers";

test("an owner sets up insurers and compares motor premiums", async ({ page }, testInfo) => {
  await newAgency(page, `calc-${testInfo.project.name}`);

  await page.goto("/settings/insurers");
  await expect(page.getByText(/awaiting adviser sign-off/)).toBeVisible();
  for (const [insurer, rate] of [["Savanna General", "4"], ["Rift Assurance", "3.5"]] as const) {
    await page.getByLabel("Insurer", { exact: true }).fill(insurer);
    await page.getByRole("button", { name: "Add insurer" }).click();
    const section = page.getByRole("region", { name: insurer });
    await section.getByRole("button", { name: "Add product" }).click();
    const sheet = page.getByRole("dialog");
    await sheet.getByLabel("Product name").fill("Motor private comprehensive");
    await sheet.getByLabel("Rate (%)").fill(rate);
    await sheet.getByLabel("Minimum premium").fill("37500");
    await sheet.getByLabel("Commission, new (%)").fill("10");
    await sheet.getByRole("button", { name: "Save product" }).click();
    await expect(section.getByText(`${rate}% of sum insured`)).toBeVisible();
  }
  await expectAccessible(page, "insurers");

  await page.goto("/calculator");
  await page.getByLabel("Sum insured").fill("2,000,000");
  await page.getByRole("button", { name: "Compare 2 quotes" }).click();
  const results = page.getByRole("region", { name: "Results" });
  // Rift: 70,000 + training 140 + PCF 175 + stamp 40 = 70,355 (cheapest first)
  await expect(results.getByRole("listitem").first()).toContainText("Rift Assurance");
  await expect(results.getByRole("listitem").first()).toContainText("KES 70,355.00");
  await expect(results.getByText(/Your commission: KES 7,000.00/)).toBeVisible();
  await expect(results.getByText(/Training levy/).first()).toBeVisible();
  await expectAccessible(page, "calculator");
});
