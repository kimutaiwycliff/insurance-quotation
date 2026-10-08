import { expect, test, type Page } from "@playwright/test";

import { expectAccessible, mailLink, uniqueEmail } from "./helpers";

/** Sign up and create an agency quickly (the golden path covers the full onboarding). */
async function newAgency(page: Page, project: string): Promise<void> {
  const email = uniqueEmail(`crm-${project}`);
  await page.goto("/sign-up");
  await page.getByLabel("Your name").fill("Achieng Otieno");
  await page.getByLabel("Email").fill(email);
  await page.getByLabel("Password").fill("correct-horse-battery-9");
  await page.getByRole("button", { name: "Create account" }).click();
  await page.goto(await mailLink(page, email, "/api/auth/verify-email"));
  await page.getByRole("link", { name: "Set up my agency" }).click();
  await page.getByLabel("Agency name").fill(`Otieno ${project} Agency`);
  await page.getByRole("button", { name: "Create agency" }).click();
  await expect(page.getByRole("heading", { name: "Agency details" })).toBeVisible();
}

test("an agent works a lead into a client and follows up", async ({ page }, testInfo) => {
  await newAgency(page, testInfo.project.name);
  const phone = `07${Math.floor(10_000_000 + Math.random() * 89_999_999)}`;

  // A lead from WhatsApp, converted to a client once won.
  await page.goto("/leads");
  await page.getByRole("button", { name: "Add lead" }).click();
  const sheet = page.getByRole("dialog");
  await sheet.getByLabel("Name").fill("Mercy Wambui");
  await sheet.getByLabel("Phone").fill(phone);
  await sheet.getByText("motor", { exact: true }).click();
  await sheet.getByLabel(/Estimated yearly premium/).fill("45000");
  await sheet.getByRole("button", { name: "Add lead" }).click();
  await expect(page.getByText("Mercy Wambui")).toBeVisible();
  await expectAccessible(page, "leads");
  await page.getByLabel("Move to: Mercy Wambui").selectOption("won");

  // The new client page opens.
  await expect(page.getByRole("heading", { name: "Mercy Wambui" })).toBeVisible();
  await expectAccessible(page, "client");

  // Log a call and add a follow-up task.
  await page.getByRole("tab", { name: "Timeline" }).click();
  await page.getByRole("radio", { name: "Phone call" }).click();
  await page.getByLabel(/What happened/).fill("Wants comprehensive cover for a 2019 Axio");
  await page.getByRole("button", { name: "Log" }).click();
  await expect(page.getByText("Wants comprehensive cover for a 2019 Axio")).toBeVisible();
  await page.getByRole("tab", { name: "Tasks" }).click();
  await page.getByLabel("Add task").fill("Send motor quote");
  await page.getByRole("button", { name: "Add task" }).click();
  await expect(page.getByText("Send motor quote")).toBeVisible();

  // Adding the same person again is caught before saving.
  await page.goto("/clients");
  await page.getByRole("button", { name: "Add client" }).click();
  const form = page.getByRole("dialog");
  await form.getByLabel("First name").fill("Mercy");
  await form.getByLabel("Last name").fill("W.");
  await form.getByLabel("Phone").fill(phone);
  await expect(form.getByText("This client may already exist")).toBeVisible();
  await expect(form.getByRole("link", { name: "Mercy Wambui" })).toBeVisible();
  await expectAccessible(page, "client form");
  await page.keyboard.press("Escape");

  // Search finds the client by the way people type phone numbers.
  await page.getByLabel(/Search by name/).fill(phone.replace(/^0/, "+254 "));
  await expect(page.getByRole("link", { name: /Mercy Wambui/ })).toBeVisible();

  // Tasks page and dashboard reflect the work.
  await page.goto("/tasks");
  await expect(page.getByText("Send motor quote")).toBeVisible();
  await page.getByRole("checkbox", { name: "Mark done: Send motor quote" }).check();
  await expect(page.getByText("Done: Send motor quote")).toBeVisible(); // confirmation toast
  await expect(page.getByRole("checkbox", { name: "Mark done: Send motor quote" })).toHaveCount(0); // leaves the open list
  await expectAccessible(page, "tasks");
  await page.goto("/");
  await expect(page.getByText("New clients in 30 days")).toBeVisible();
});
