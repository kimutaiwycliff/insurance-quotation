import { expect, test } from "@playwright/test";

import { expectAccessible, newAgency } from "./helpers";

test("a business connects M-Pesa and gets paid from the app and from the invoice link", async ({ page, browser }, testInfo) => {
  test.setTimeout(180_000);
  await newAgency(page, `mpesa-${testInfo.project.name}`);

  // Connect M-Pesa (the simulator stands in for Safaricom).
  await page.goto("/settings/payments");
  await expect(page.getByText("Coming soon")).toBeVisible(); // cards
  await page.getByLabel("Account").selectOption("simulator");
  await page.getByLabel("Paybill number").fill("174379");
  await page.getByLabel("Consumer key").fill("simulator-key-0001");
  await page.getByLabel("Consumer secret").fill("simulator-secret-0001");
  await page.getByLabel("Passkey").fill("simulator-passkey-0001");
  await page.getByRole("button", { name: "Connect M-Pesa" }).click();
  await expect(page.getByText("Connected", { exact: true })).toBeVisible();
  await expectAccessible(page, "payment settings");

  // A client and two invoices.
  await page.goto("/clients");
  await page.getByRole("button", { name: "Add client" }).click();
  const form = page.getByRole("dialog");
  await form.getByLabel("First name").fill("Wanjiru");
  await form.getByLabel("Last name").fill("Kamau");
  await form.getByLabel("Phone").fill("0712 345 678");
  await form.getByRole("button", { name: "Save client" }).click();
  await expect(page.getByRole("heading", { name: "Wanjiru Kamau" })).toBeVisible();
  const clientUrl = page.url();
  for (const amount of ["1000", "2500"]) {
    await page.goto(clientUrl);
    await page.getByRole("link", { name: "New invoice" }).click();
    await page.getByLabel("Description for line 1").fill("Service");
    await page.getByLabel("Price for line 1").fill(amount);
    await page.getByRole("button", { name: "Save draft invoice" }).click();
    await page.getByRole("button", { name: "Issue" }).click();
    await expect(page.getByRole("heading", { name: /Invoice INV-/ })).toBeVisible();
  }

  // From the app: a payment prompt to the client's phone.
  await page.getByRole("button", { name: "Ask for M-Pesa payment" }).click();
  const dialog = page.getByRole("dialog");
  await expect(dialog.getByLabel("Client's M-Pesa number")).toHaveValue("0712 345 678");
  await dialog.getByRole("button", { name: "Send prompt" }).click();
  await expect(dialog.getByText(/Paid\. The payment is recorded/)).toBeVisible({ timeout: 30_000 });
  await dialog.getByRole("button", { name: "Done" }).click();
  await expect(page.getByText("Paid", { exact: true }).first()).toBeVisible(); // status badge

  // From the link: the client pays the other invoice on their phone.
  await page.goto(clientUrl);
  await page.getByRole("tab", { name: "Invoices" }).click();
  await page.getByRole("link", { name: /INV-.*/ }).filter({ hasText: "Unpaid" }).first().click();
  await page.getByRole("button", { name: "Send" }).click();
  await page.getByRole("dialog").getByRole("button", { name: "Send" }).click();
  const link = await page.getByLabel("Link").inputValue();
  const visitor = await (await browser.newContext({ viewport: { width: 390, height: 844 } })).newPage();
  await visitor.goto(new URL(link).pathname);
  await expect(visitor.getByRole("heading", { name: "Pay KES 1,160.00" })).toBeVisible();
  await expect(visitor.getByText("Card payments coming soon")).toBeVisible();
  await expectAccessible(visitor, "public invoice payment");
  await visitor.getByLabel("Your M-Pesa number").fill("0712345678");
  await visitor.getByRole("button", { name: "Pay with M-Pesa" }).click();
  await expect(visitor.getByText("This invoice is paid. Thank you.")).toBeVisible({ timeout: 30_000 });
  await visitor.close();
});
