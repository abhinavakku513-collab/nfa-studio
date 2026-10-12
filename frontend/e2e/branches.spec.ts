import AxeBuilder from "@axe-core/playwright";
import { type Page, expect, test } from "@playwright/test";

async function build(page: Page, prompt: string): Promise<void> {
  await page.goto("/");
  const box = page.getByLabel(/describe a set of strings/i);
  await box.fill(prompt);
  await box.press("Control+Enter");
  await expect(page.getByRole("region", { name: "Confirm" })).toContainText(
    "Strings over",
  );
  await page.getByRole("button", { name: "Build and verify" }).click();
  await expect(page.getByText(/^V\d · /)).toBeVisible({ timeout: 30_000 });
}

async function openBranches(page: Page, count: number): Promise<void> {
  const toggle = page.getByRole("button", { name: `Branches (${count})` });
  await toggle.click();
  await expect(toggle).toHaveAttribute("aria-pressed", "true");
}

async function simulate(page: Page, word: string): Promise<void> {
  const input = page.getByLabel("Word to simulate");
  await input.fill(word);
  await input.press("Enter");
}

const lane = (page: Page, n: number) =>
  page.getByRole("region", { name: new RegExp(`^Branch ${n}: `) });
const combined = (page: Page) => page.getByText(/^Combined verdict: /);

test("contains 101 and ends with 00: one lane per condition, ALL must accept", async ({
  page,
}) => {
  await build(page, "contains 101 and ends with 00");
  await openBranches(page, 2);
  await expect(lane(page, 1)).toHaveAccessibleName("Branch 1: contain 101");
  await expect(lane(page, 2)).toHaveAccessibleName("Branch 2: end with 00");
  await expect(page.getByText("ALL must accept")).toBeVisible();

  const cases: [string, string, string, RegExp, string][] = [
    ["10100", "Accepts", "Accepts", /accepted/, "Accepted"],
    [
      "101",
      "Accepts",
      "Rejects",
      /rejected; .*branch 2 \(end with 00\)/,
      "Rejected",
    ],
    ["10101", "Accepts", "Rejects", /rejected/, "Rejected"],
  ];
  for (const [word, first, second, verdict, main] of cases) {
    await simulate(page, word);
    await expect(combined(page)).toHaveText(verdict, { timeout: 30_000 });
    await expect(lane(page, 1).getByText(first, { exact: true })).toBeVisible();
    await expect(
      lane(page, 2).getByText(second, { exact: true }),
    ).toBeVisible();
    // The main automaton agrees with the combined verdict.
    await expect(page.getByRole("status", { name: "Verdict" })).toHaveText(
      main,
    );
  }

  // One control moves every lane: back to the start, both lanes sit in q0.
  await page.getByRole("button", { name: "Jump to start (Home)" }).click();
  await expect(lane(page, 1).getByText("{q0}")).toBeVisible();
  await expect(lane(page, 2).getByText("{q0}")).toBeVisible();
  await expect(lane(page, 1).getByText("Accepts")).toHaveCount(0);
});

test("contains 101 or ends with 00: ANY accepts", async ({ page }) => {
  await build(page, "contains 101 or ends with 00");
  await openBranches(page, 2);
  await expect(
    page.getByRole("group", {
      name: "2 branches; one accepting branch is enough",
    }),
  ).toBeVisible();
  await simulate(page, "101");
  await expect(combined(page)).toHaveText(
    /^Combined verdict: accepted; .*branch 1 \(contain 101\) accepts/,
    { timeout: 30_000 },
  );
  await expect(page.getByText("ANY accepts")).toBeVisible();
});

test("the Branches view passes axe after a run", async ({ page }) => {
  await build(page, "contains 101 but does not end with 00");
  await openBranches(page, 2);
  await expect(lane(page, 2)).toHaveAccessibleName("Branch 2: NOT end with 00");
  await simulate(page, "10100");
  await expect(combined(page)).toHaveText(/rejected/, { timeout: 30_000 });
  const results = await new AxeBuilder({ page })
    .withTags(["wcag2a", "wcag2aa", "wcag21a", "wcag21aa", "wcag22aa"])
    .analyze();
  const found = results.violations.map(
    (v) =>
      `${v.id} (${v.impact}): ${v.nodes.map((n) => n.target.join(" ")).join(", ")}`,
  );
  expect(found).toEqual([]);
});
