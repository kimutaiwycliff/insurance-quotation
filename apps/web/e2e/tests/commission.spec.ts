import { expect, test } from "@playwright/test";

import { expectAccessible, newAgency } from "./helpers";

function phone(): string {
  return `07${Math.floor(10_000_000 + Math.random() * 89_999_999)}`;
}

test("an agent imports their book and records commission from an insurer", async ({ page }, testInfo) => {
  await newAgency(page, `commission-${testInfo.project.name}`);

  // Import two existing policies from a spreadsheet saved as CSV.
  await page.goto("/policies");
  await page.getByRole("link", { name: "Import from a spreadsheet" }).click();
  const csv = [
    "Insured Name,Mobile,Insurance Company,Cover Type,Policy No,Reg No,Inception Date,Gross Premium,Comm %,Basic Premium",
    `Wanjiru Kamau,${phone()},Savanna General,Motor - Comprehensive,SG/1,KDA 123A,01/09/2026,"35,195",10%,"35,000"`,
    `Acacia Traders Ltd,${phone()},Savanna General,WIBA,SG/2,Staff WIBA,15/09/2026,25000,10,25000`,
    "Kamau,0700000000,Savanna General,Motor,SG/3,KCB 1,not a date,1000,,",
  ].join("\n");
  await page.locator('input[type="file"]').setInputFiles({ name: "book.csv", mimeType: "text/csv", buffer: Buffer.from(csv) });
  await expect(page.getByText(/2 ready \(/)).toBeVisible();
  await expect(page.getByText(/Cannot read the date/)).toBeVisible();
  await expectAccessible(page, "import preview");
  await page.getByLabel(/leave out the rows with errors/).check();
  await page.getByRole("button", { name: "Import 2 policies" }).click();
  await expect(page.getByRole("heading", { name: "Book imported" })).toBeVisible();
  await expect(page.getByText(/2 policies added, 2 new clients/)).toBeVisible();

  // Commission: KES 3,500 + 2,500 expected, 10% WHT withheld → 5,400 net owed.
  await page.goto("/commission");
  await expect(page.getByText("KES 5,400.00").first()).toBeVisible();
  await expectAccessible(page, "commission");
  await page.getByRole("button", { name: "Record commission" }).click();
  const sheet = page.getByRole("dialog");
  await sheet.getByLabel("WHT certificate number").fill("KRAWHT0099");
  await expect(sheet.getByText("KES 6,000.00")).toBeVisible();
  await sheet.getByRole("button", { name: "Record commission" }).click();
  await expect(page.getByText("Insurers have paid everything they owe you.")).toBeVisible();
  await expect(page.getByRole("region", { name: "WHT certificates" }).getByText("KRAWHT0099")).toBeVisible();

  // The home page shows the year's book.
  await page.goto("/");
  await expect(page.getByRole("heading", { name: "This year" })).toBeVisible();
  await expect(page.getByText("KES 60,195.00")).toBeVisible();
});
