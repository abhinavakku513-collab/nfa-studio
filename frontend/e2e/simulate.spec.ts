import { type Page, expect, test } from "@playwright/test";

type Case = {
  prompt: string;
  /** The option to pick if the studio asks a question. */
  answer?: string;
  accepted: string;
  rejected: string;
};

const CASES: Case[] = [
  { prompt: "binary strings ending in 01", accepted: "1101", rejected: "0110" },
  {
    prompt: "strings over {a,b} not containing aa",
    accepted: "abab",
    rejected: "baab",
  },
  { prompt: "(ab)* over {a,b}", accepted: "abab", rejected: "aba" },
  {
    prompt: "strings over {a,b} with an even number of a's that end with b",
    accepted: "aab",
    rejected: "ab",
  },
  {
    prompt: "strings over {a,b} that contain aba twice",
    answer: "Yes, overlap allowed",
    accepted: "ababa",
    rejected: "abab",
  },
];

async function describeAndBuild(page: Page, item: Case): Promise<void> {
  await page.goto("/");
  const box = page.getByLabel(/describe a set of strings/i);
  await box.fill(item.prompt);
  await box.press("Control+Enter");
  if (item.answer) {
    await page.getByRole("button", { name: item.answer }).click();
  }
  await expect(page.getByRole("region", { name: "Confirm" })).toContainText(
    "Strings over",
  );
  await page.getByRole("button", { name: "Build and verify" }).click();
  await expect(page.getByText(/^V\d · /)).toBeVisible({ timeout: 30_000 });
  await expect(page.locator(".diagram svg")).toBeVisible();
}

async function simulate(
  page: Page,
  word: string,
  verdict: "Accepted" | "Rejected",
): Promise<void> {
  const input = page.getByLabel("Word to simulate");
  await input.fill(word);
  await input.press("Enter");
  // The token layer is drawn inside the Graphviz group while the word plays.
  await expect(page.locator(".diagram .sim-token").first()).toBeAttached();
  await expect(page.getByRole("status", { name: "Verdict" })).toHaveText(
    verdict,
    { timeout: 30_000 },
  );
  await expect(page.getByText(/^Step \d+: /)).toHaveText(
    new RegExp(
      `^Step ${word.length}: read ${word.at(-1)}, active .*\\. ${verdict}\\.$`,
    ),
  );
}

for (const item of CASES) {
  test(`${item.prompt}: describe, confirm, build, simulate`, async ({
    page,
  }) => {
    const errors: string[] = [];
    page.on("pageerror", (error) => errors.push(String(error)));

    await describeAndBuild(page, item);

    await simulate(page, item.accepted, "Accepted");
    await expect(
      page.locator(".diagram .state.is-active").first(),
    ).toBeAttached();
    await expect(
      page.locator(".diagram .edge.is-witness").first(),
    ).toBeAttached();

    await page.getByLabel("Speed").selectOption("4");
    await simulate(page, item.rejected, "Rejected");
    await expect(page.locator(".diagram .edge.is-witness")).toHaveCount(0);

    const history = page.getByRole("region", { name: "Tested words" });
    await expect(history.getByRole("listitem")).toHaveText([
      new RegExp(`Rejected${item.rejected}`),
      new RegExp(`Accepted${item.accepted}`),
    ]);
    expect(errors).toEqual([]);
  });
}
