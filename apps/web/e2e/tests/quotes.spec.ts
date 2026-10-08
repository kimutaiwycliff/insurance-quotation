import { expect, test } from "@playwright/test";

import { expectAccessible, newAgency } from "./helpers";

test("an agent sends a comparison quote and the client accepts it", async ({ page, browser }, testInfo) => {
  await newAgency(page, `quote-${testInfo.project.name}`);

  // Two insurers with motor products.
  await page.goto("/settings/insurers");
  for (const [insurer, rate] of [["Savanna General", "4"], ["Rift Assurance", "3.5"]] as const) {
    await page.getByLabel("Insurer", { exact: true }).fill(insurer);
    await page.getByRole("button", { name: "Add insurer" }).click();
    const section = page.getByRole("region", { name: insurer });
    await section.getByRole("button", { name: "Add product" }).click();
    const sheet = page.getByRole("dialog");
    await sheet.getByLabel("Product name").fill("Motor comprehensive");
    await sheet.getByLabel("Rate (%)").fill(rate);
    await sheet.getByLabel("Commission, new (%)").fill("10");
    await sheet.getByRole("button", { name: "Save product" }).click();
    await expect(section.getByText(`${rate}% of sum insured`)).toBeVisible();
  }

  // A client, then a quote comparing both insurers.
  await page.goto("/clients");
  await page.getByRole("button", { name: "Add client" }).click();
  const form = page.getByRole("dialog");
  await form.getByLabel("First name").fill("Otieno");
  await form.getByLabel("Last name").fill("Ochieng");
  await form.getByLabel("Phone").fill(`07${Math.floor(10_000_000 + Math.random() * 89_999_999)}`);
  await form.getByRole("button", { name: "Save client" }).click();
  await page.getByRole("link", { name: "New quote" }).click();
  await page.getByLabel("Savanna General: Motor comprehensive").or(page.getByLabel("Motor comprehensive").first()).first().check();
  for (const box of await page.getByRole("checkbox", { name: "Motor comprehensive" }).all()) await box.check();
  await page.getByLabel("Sum insured").fill("2000000");
  await page.getByLabel("Vehicle").fill("KDA 123A, Toyota Axio 2019");
  await page.getByRole("button", { name: "Create quote" }).click();

  await expect(page.getByRole("heading", { name: "Motor private quotation" })).toBeVisible();
  const options = page.getByRole("list", { name: "Options" });
  await expect(options.getByRole("listitem").first()).toContainText("Rift Assurance");
  await expect(options.getByRole("listitem").first()).toContainText("KES 70,355.00");
  await expect(page.getByText(/Your commission/).first()).toBeVisible();
  await expectAccessible(page, "quote");

  // Send without email: get the link to share.
  await page.getByRole("button", { name: "Send to client" }).click();
  await page.getByRole("button", { name: "Send quote" }).click();
  const link = await page.getByLabel("Quote link").inputValue();
  expect(link).toMatch(/\/d\/[A-Za-z0-9_-]{43}$/);
  await expect(page.getByRole("link", { name: "Share on WhatsApp" })).toBeVisible();

  // The client opens the link (no account, fresh browser) and accepts the cheaper option.
  const client = await browser.newContext({ viewport: { width: 390, height: 844 } });
  const visitor = await client.newPage();
  await visitor.goto(new URL(link).pathname);
  await expect(visitor.getByRole("heading", { name: /Quotation QT-/ })).toBeVisible();
  await expect(visitor.getByText(/ommission/)).toHaveCount(0); // never shown to clients
  await expectAccessible(visitor, "public quote");
  await visitor.getByRole("radio", { name: /Rift Assurance/ }).check();
  await visitor.getByLabel("Your full name").fill("Otieno Ochieng");
  await visitor.getByLabel(/I accept this option/).check();
  await visitor.getByRole("button", { name: "Accept option 1" }).click();
  await expect(visitor.getByText(/You accepted this quotation/)).toBeVisible();
  await client.close();

  // The agent sees the acceptance.
  await page.keyboard.press("Escape");
  await page.reload();
  await expect(page.getByText(/Accepted option 1 by/)).toBeVisible();
  await expect(page.getByText("Accepted", { exact: true })).toBeVisible();
});
