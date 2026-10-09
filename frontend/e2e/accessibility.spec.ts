import AxeBuilder from "@axe-core/playwright";
import { type Locator, type Page, expect, test } from "@playwright/test";

/** Press Tab until `target` has focus, checking each stop shows a focus ring. */
async function tabTo(page: Page, target: Locator, limit = 60): Promise<number> {
  const handle = await target.elementHandle();
  for (let presses = 1; presses <= limit; presses++) {
    await page.keyboard.press("Tab");
    const stop = await page.evaluate((wanted) => {
      const element = document.activeElement as HTMLElement | null;
      const style = element ? getComputedStyle(element) : null;
      return {
        reached: element === wanted,
        name:
          element?.getAttribute("aria-label") ??
          element?.textContent?.trim().slice(0, 40) ??
          "",
        ring:
          style !== null &&
          style.outlineStyle !== "none" &&
          style.outlineWidth !== "0px",
      };
    }, handle);
    expect(stop.ring, `focus ring on "${stop.name}"`).toBe(true);
    if (stop.reached) {
      return presses;
    }
  }
  throw new Error(`Tab never reached ${String(target)}`);
}

const status = (page: Page) => page.getByText(/^Step \d+: /);

test("keyboard alone reaches all five steps, in reading order", async ({
  page,
}) => {
  await page.goto("/");

  // The skip link is the first stop and moves focus to the automaton.
  await page.keyboard.press("Tab");
  await expect(
    page.getByRole("link", { name: "Skip to the automaton" }),
  ).toBeFocused();

  // 1. Describe
  const description = page.getByLabel(/describe a set of strings/i);
  await tabTo(page, description);
  await page.keyboard.type("binary strings ending in 01");
  await page.keyboard.press("Control+Enter");

  // 2. Confirm: the reading's chips are buttons in the tab order.
  const confirm = page.getByRole("region", { name: "Confirm" });
  await expect(confirm).toContainText("Strings over");
  await tabTo(page, confirm.getByRole("button", { name: /suffix: 01/ }));

  // 3. Build
  await tabTo(page, page.getByRole("button", { name: "Build and verify" }));
  await page.keyboard.press("Enter");
  await expect(page.getByText(/^V\d · /)).toBeVisible({ timeout: 30_000 });

  // 4. Explore: arrow keys move between the tabs, the diagram zooms from the keyboard.
  const diagramTab = page.getByRole("tab", { name: "Diagram" });
  await tabTo(page, diagramTab);
  await page.keyboard.press("ArrowRight");
  await expect(page.getByRole("tab", { name: "Table" })).toBeFocused();
  await expect(page.getByRole("table")).toBeVisible();
  await page.keyboard.press("End");
  await expect(page.getByRole("tab", { name: "Explanation" })).toHaveAttribute(
    "aria-selected",
    "true",
  );
  await page.keyboard.press("Home");
  await expect(diagramTab).toHaveAttribute("aria-selected", "true");
  const viewport = page.getByRole("group", { name: /^State diagram\./ });
  await tabTo(page, viewport);
  await page.keyboard.press("+");
  await expect(page.getByText("125%")).toBeVisible();
  await page.keyboard.press("0");
  await expect(page.getByText("100%")).toBeVisible();

  // 5. Simulate
  await tabTo(page, page.getByLabel("Word to simulate"));
  await page.keyboard.type("1101");
  await page.keyboard.press("Enter");
  await expect(page.getByRole("status", { name: "Verdict" })).toHaveText(
    "Accepted",
    {
      timeout: 30_000,
    },
  );
  await tabTo(page, page.getByRole("group", { name: /^Input tape/ }));
  await page.keyboard.press("Home");
  await expect(status(page)).toHaveText("Step 0: start, active {q0}");
  await page.keyboard.press("ArrowRight");
  await expect(status(page)).toHaveText(/^Step 1: read 1, active /);
  await page.keyboard.press("End");
  await expect(status(page)).toHaveText(/^Step 4: read 1, .*\. Accepted\.$/);
});

async function axe(page: Page, state: string): Promise<void> {
  // Colours sampled halfway through a transition (busy → enabled) are not a real state.
  await page.waitForFunction(() =>
    document.getAnimations().every((a) => a.playState !== "running"),
  );
  const results = await new AxeBuilder({ page })
    .withTags(["wcag2a", "wcag2aa", "wcag21a", "wcag21aa", "wcag22aa"])
    .analyze();
  const found = results.violations.map(
    (v) =>
      `${v.id} (${v.impact}): ${v.nodes.map((n) => n.target.join(" ")).join(", ")}`,
  );
  expect(found, `axe violations in ${state}`).toEqual([]);
}

async function describe(page: Page, text: string): Promise<void> {
  const box = page.getByLabel(/describe a set of strings/i);
  await box.fill(text);
  await box.press("Control+Enter");
}

for (const theme of ["light", "dark"] as const) {
  test(`no axe violations in the ${theme} theme`, async ({ page }) => {
    await page.emulateMedia({ colorScheme: theme });
    await page.goto("/");
    await expect(page.locator("html")).toHaveAttribute("data-theme", theme);
    await axe(page, "the empty page");

    await describe(page, "same number of a's and b's");
    await expect(
      page.getByRole("region", { name: "Describe" }).getByRole("alert"),
    ).toContainText("not regular");
    await axe(page, "a refusal with an alternative");

    await describe(page, "strings over {a,b} that contain two a's");
    await expect(page.getByText(/^Question 1/)).toBeVisible();
    await axe(page, "a clarification question");
    await page.getByRole("button", { name: /exactly/i }).click();

    await page.getByRole("button", { name: "Build and verify" }).click();
    await expect(page.getByText(/^V\d · /)).toBeVisible({ timeout: 30_000 });
    await expect(page.locator(".diagram svg")).toBeVisible();
    const word = page.getByLabel("Word to simulate");
    await word.fill("abab");
    await word.press("Enter");
    await expect(page.getByRole("status", { name: "Verdict" })).toHaveText(
      "Accepted",
      {
        timeout: 30_000,
      },
    );
    await word.fill("abcb");
    await page.getByText("Batch test").click();
    await page.getByLabel(/Words, one per line/).fill("aa\nab\nε\nac");
    await page.getByRole("button", { name: "Run batch" }).click();
    await expect(page.getByText(/accepted, .* rejected/)).toBeVisible();
    await axe(page, "the diagram after a simulation, a bad word and a batch");

    for (const tab of ["Table", "Formal definition", "Explanation"]) {
      await page.getByRole("tab", { name: tab }).click();
      await expect(page.getByRole("tabpanel")).not.toContainText("Loading");
      await axe(page, `the ${tab} tab`);
    }
  });
}
