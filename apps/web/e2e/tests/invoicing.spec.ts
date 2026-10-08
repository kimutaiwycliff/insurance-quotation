import { expect, test } from "@playwright/test";

import { expectAccessible, newAgency } from "./helpers";

test("an owner invoices a client, records payments and the client sees the invoice", async ({ page, browser }, testInfo) => {
  await newAgency(page, `invoice-${testInfo.project.name}`);

  // An item in the catalogue.
  await page.goto("/settings/items");
  await page.getByRole("button", { name: "Add item" }).click();
  const itemDialog = page.getByRole("dialog");
  await itemDialog.getByLabel("Name").fill("Monthly bookkeeping");
  await itemDialog.getByLabel("Price").fill("1500");
  await itemDialog.getByRole("button", { name: "Save item" }).click();
  await expect(page.getByText("KES 1,500.00")).toBeVisible();

  // A client and a draft invoice: 3 months of bookkeeping with 10% off (VAT 16% on top).
  await page.goto("/clients");
  await page.getByRole("button", { name: "Add client" }).click();
  const form = page.getByRole("dialog");
  await form.getByLabel("First name").fill("Wanjiru");
  await form.getByLabel("Last name").fill("Kamau");
  await form.getByLabel("Phone").fill(`07${Math.floor(10_000_000 + Math.random() * 89_999_999)}`);
  await form.getByRole("button", { name: "Save client" }).click();
  await page.getByRole("link", { name: "New invoice" }).click();
  await page.getByLabel("Item for line 1").selectOption({ label: "Monthly bookkeeping" });
  await page.getByLabel("Quantity for line 1").fill("3");
  await page.getByLabel("Discount % for line 1").fill("10");
  await page.getByRole("button", { name: "Save draft invoice" }).click();
  await expect(page.getByRole("heading", { name: "Invoice (draft)" })).toBeVisible();
  await expect(page.getByText("KES 4,698.00")).toBeVisible(); // 4,050 + 648 VAT
  await expectAccessible(page, "draft invoice");

  // Issue, then record a partial M-Pesa payment.
  await page.getByRole("button", { name: "Issue" }).click();
  await expect(page.getByRole("heading", { name: /Invoice INV-/ })).toBeVisible();
  await expect(page.getByText("Unpaid", { exact: true })).toBeVisible();
  await page.getByRole("button", { name: "Record payment" }).click();
  const pay = page.getByRole("dialog");
  await pay.getByLabel("Amount (KES)").fill("2000");
  await pay.getByLabel("Reference").fill("SJK12AB34C");
  await pay.getByRole("button", { name: "Record payment" }).click();
  await expect(page.getByText("Part paid", { exact: true })).toBeVisible();
  await expect(page.getByText("KES 2,698.00")).toBeVisible();

  // Send it: the client opens the link without an account.
  await page.getByRole("button", { name: "Send" }).click();
  await page.getByRole("dialog").getByRole("button", { name: "Send" }).click();
  const link = await page.getByLabel("Link").inputValue();
  await page.keyboard.press("Escape");
  const visitor = await (await browser.newContext({ viewport: { width: 390, height: 844 } })).newPage();
  await visitor.goto(new URL(link).pathname);
  await expect(visitor.getByRole("heading", { name: /Invoice INV-/ })).toBeVisible();
  await expectAccessible(visitor, "public invoice");
  await visitor.close();

  // The rest is paid: the invoice is settled and listed under payments.
  await page.getByRole("button", { name: "Record payment" }).click();
  await page.getByRole("dialog").getByRole("button", { name: "Record payment" }).click();
  await expect(page.getByText("Paid", { exact: true })).toBeVisible();
  await page.goto("/payments");
  await expect(page.getByRole("list", { name: "Payments" }).getByRole("listitem")).toHaveCount(2);
  await expectAccessible(page, "payments");
});
