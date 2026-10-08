import AxeBuilder from "@axe-core/playwright";
import { expect, type Page } from "@playwright/test";

const MAILPIT = process.env.E2E_MAILPIT_URL ?? "http://localhost:8025";

/** WCAG 2.2 AA via axe: no serious or critical violations (plan W1 acceptance). */
export async function expectAccessible(page: Page, context: string): Promise<void> {
  // Colour contrast is only meaningful at rest: a toast caught mid-fade (opacity < 1) reads as low contrast.
  // Let running CSS transitions and animations finish first (infinite ones, such as spinners, are skipped).
  await page.evaluate(() =>
    Promise.all(
      document
        .getAnimations()
        .filter((a) => a.effect?.getComputedTiming().iterations !== Infinity)
        .map((a) => a.finished.catch(() => undefined)),
    ),
  );
  // Sandboxed iframes (document previews) cannot run axe's script and would hang the scan; their content is
  // generated documents, covered by the template tests.
  const results = await new AxeBuilder({ page })
    .withTags(["wcag2a", "wcag2aa", "wcag21aa", "wcag22aa"])
    .exclude("iframe[sandbox]")
    .analyze();
  const serious = results.violations.filter((v) => v.impact === "serious" || v.impact === "critical");
  expect(
    serious.flatMap((v) =>
      v.nodes.map((n) => `${context}: ${v.id} at ${n.target.join(" ")}: ${n.failureSummary?.replace(/\s+/g, " ")}`),
    ),
  ).toEqual([]);
}

/** The newest link in an email to `to` whose URL contains `fragment`. */
export async function mailLink(page: Page, to: string, fragment: string): Promise<string> {
  for (let attempt = 0; attempt < 40; attempt++) {
    const search = await page.request.get(`${MAILPIT}/api/v1/search`, { params: { query: `to:${to}` } });
    const { messages = [] } = (await search.json()) as { messages?: { ID: string }[] };
    for (const message of messages) {
      const body = (await (await page.request.get(`${MAILPIT}/api/v1/message/${message.ID}`)).json()) as { Text: string };
      const match = body.Text.match(new RegExp(`https?://\\S*${fragment.replace(/[/?]/g, "\\$&")}\\S*`));
      if (match) return match[0];
    }
    await page.waitForTimeout(250);
  }
  throw new Error(`No email to ${to} containing ${fragment}`);
}

export function uniqueEmail(prefix: string): string {
  return `${prefix}-${Date.now().toString(36)}${Math.random().toString(36).slice(2, 6)}@example.com`;
}

/** Sign up and create an agency quickly (the golden path covers the full onboarding). */
export async function newAgency(page: Page, project: string): Promise<void> {
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

