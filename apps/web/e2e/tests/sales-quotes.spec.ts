import { expect, test } from "@playwright/test";

import { expectAccessible, newAgency } from "./helpers";

test("a business sends a quote with an optional extra; the client accepts it and it becomes an invoice", async ({ page, browser }, testInfo) => {
  await newAgency(page, `salesquote-${testInfo.project.name}`);

  await page.goto("/clients");
  await page.getByRole("button", { name: "Add client" }).click();
  const form = page.getByRole("dialog");
  await form.getByLabel("First name").fill("Otieno");
  await form.getByLabel("Last name").fill("Ochieng");
  await form.getByLabel("Phone").fill(`07${Math.floor(10_000_000 + Math.random() * 89_999_999)}`);
  await form.getByRole("button", { name: "Save client" }).click();
  await page.getByRole("tab", { name: "Invoices" }).click();
  await page.getByRole("link", { name: "New sales quote" }).click();

  // Website design, plus optional hosting the client may add.
  await page.getByLabel("Heading for line 1").fill("Design");
  await page.getByLabel("Description for line 1").fill("Website design");
  await page.getByLabel("Price for line 1").fill("40000");
  await page.getByRole("button", { name: "Add line" }).click();
  await page.getByLabel("Description for line 2").fill("Hosting, first year");
  await page.getByLabel("Price for line 2").fill("5000");
  await page.getByText("Optional extra (the client chooses; not in the total)").nth(1).click();
  await page.getByRole("button", { name: "Save draft quote" }).click();
  await expect(page.getByRole("heading", { name: "Sales quote (draft)" })).toBeVisible();
  await expect(page.getByText("KES 46,400.00")).toBeVisible(); // 40,000 + 16% VAT
  await expect(page.getByText("Optional", { exact: true })).toBeVisible();
  await expectAccessible(page, "draft sales quote");

  await page.getByRole("button", { name: "Send to client" }).click();
  await page.getByRole("dialog").getByRole("button", { name: "Send" }).click();
  const link = await page.getByLabel("Link").inputValue();
  await page.keyboard.press("Escape");

  const visitor = await (await browser.newContext({ viewport: { width: 390, height: 844 } })).newPage();
  await visitor.goto(new URL(link).pathname);
  await expect(visitor.getByRole("heading", { name: /Quotation QT-/ })).toBeVisible();
  await visitor.getByRole("checkbox", { name: /Hosting, first year/ }).check();
  await visitor.getByLabel("Your full name").fill("Otieno Ochieng");
  await visitor.getByLabel(/I accept this quotation/).check();
  await expectAccessible(visitor, "public sales quote");
  await visitor.getByRole("button", { name: "Accept quotation" }).click();
  await expect(visitor.getByText(/You accepted this quotation/)).toBeVisible();
  await visitor.close();

  await page.reload();
  await expect(page.getByText(/Accepted by/)).toBeVisible();
  await expect(page.getByText(/with Hosting, first year/)).toBeVisible();
  await page.getByRole("button", { name: "Create invoice" }).click();
  await expect(page.getByRole("heading", { name: "Invoice (draft)" })).toBeVisible();
  await expect(page.getByText("KES 52,200.00")).toBeVisible(); // with the hosting
});
