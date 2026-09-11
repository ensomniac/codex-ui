const { test, expect } = require("@playwright/test");
const AxeBuilder = require("@axe-core/playwright").default;

for (const width of [320, 390, 768, 1440]) {
  test(`home and guide remain readable at ${width}px`, async ({ page }) => {
    await page.setViewportSize({ width, height: 900 });
    for (const route of ["/", "/guide.html"]) {
      await page.goto(route);
      expect(
        await page.evaluate(
          () => document.documentElement.scrollWidth <= innerWidth,
        ),
      ).toBe(true);
      const failures = (
        await new AxeBuilder({ page })
          .withTags(["wcag2a", "wcag2aa", "wcag21aa"])
          .analyze()
      ).violations;
      expect(
        failures.map((v) => ({
          id: v.id,
          nodes: v.nodes.map((n) => ({
            target: n.target,
            summary: n.failureSummary,
          })),
        })),
      ).toEqual([]);
    }
  });
}
test("example reports actual page state and resets", async ({ page }) => {
  await page.goto("/");
  await expect(page.locator("#state-value")).toHaveText("not_reviewed");
  await page
    .getByRole("button", { name: "Mark reviewed", exact: true })
    .click();
  await expect(page.locator("#review-status")).toHaveText("Reviewed");
  await expect(page.locator("#activation-count")).toHaveText("1");
  await page
    .getByRole("button", { name: "Mark reviewed", exact: true })
    .click();
  await expect(page.locator("#activation-count")).toHaveText("2");
  await page.getByRole("button", { name: "Reset example" }).click();
  await expect(page.locator("#state-value")).toHaveText("not_reviewed");
  await expect(
    page.getByRole("button", { name: "Mark reviewed", exact: true }),
  ).toBeFocused();
  await expect(page.locator(".demo-console")).not.toContainText(
    "pointer_restored",
  );
});
test("install methods support keyboard selection and real clipboard content", async ({
  page,
  context,
}) => {
  await context.grantPermissions(["clipboard-read", "clipboard-write"]);
  await page.goto("/#install");
  await page.getByRole("tab", { name: "Installer", exact: true }).focus();
  await page.keyboard.press("ArrowRight");
  await expect(
    page.getByRole("tab", { name: "Homebrew", exact: true }),
  ).toHaveAttribute("aria-selected", "true");
  await page
    .getByRole("tabpanel")
    .getByRole("button", { name: "Copy command" })
    .click();
  expect(await page.evaluate(() => navigator.clipboard.readText())).toContain(
    "brew install ensomniac/codex-ui/codex-ui",
  );
  await page.getByRole("tab", { name: "Homebrew", exact: true }).focus();
  await page.keyboard.press("End");
  await expect(page.getByRole("tabpanel")).toContainText("npm install -g");
  await page.keyboard.press("Home");
  await expect(page.getByRole("tabpanel")).toContainText("curl -fsSL");
});
test("copy failure selects the actual command", async ({ page }) => {
  await page.addInitScript(() => {
    Object.defineProperty(navigator, "clipboard", {
      value: {
        writeText: async () => {
          throw new Error("denied");
        },
      },
    });
  });
  await page.goto("/");
  await page.locator("#panel-installer [data-copy]").click();
  await expect(page.locator("#copy-message")).toHaveText(
    "Command selected. Use your copy shortcut.",
  );
  expect(await page.evaluate(() => getSelection().toString())).toContain(
    "curl -fsSL",
  );
});
test("without JavaScript every install recipe and guide remains available", async ({
  browser,
}) => {
  const context = await browser.newContext({
    javaScriptEnabled: false,
    viewport: { width: 390, height: 844 },
  });
  const page = await context.newPage();
  await page.goto("http://127.0.0.1:4198/");
  for (const id of ["installer", "brew", "uv", "npm"])
    await expect(page.locator(`#panel-${id}`)).toBeVisible();
  await expect(page.getByRole("tablist")).toBeHidden();
  await page.getByText("Which agents can use it?", { exact: true }).click();
  await expect(page.locator(".faq details").first()).toHaveAttribute(
    "open",
    "",
  );
  await page.goto("http://127.0.0.1:4198/guide.html");
  await expect(
    page.getByRole("heading", { name: "Your first action" }),
  ).toBeVisible();
  await context.close();
});
test("reduced motion retains content and disables animated scrolling", async ({
  page,
}) => {
  await page.emulateMedia({ reducedMotion: "reduce" });
  await page.goto("/");
  expect(
    await page.evaluate(
      () => getComputedStyle(document.documentElement).scrollBehavior,
    ),
  ).toBe("auto");
  await expect(page.getByRole("heading", { level: 1 })).toBeVisible();
});
test("internal guide anchors and local assets resolve", async ({
  page,
  request,
}) => {
  for (const route of ["/", "/guide.html"]) {
    const errors = [];
    page.on("pageerror", (error) => errors.push(error.message));
    await page.goto(route);
    const links = await page
      .locator('a[href],img[src],link[rel="stylesheet"],script[src]')
      .evaluateAll((nodes) =>
        nodes.map((node) => node.href || node.src).filter(Boolean),
      );
    for (const value of new Set(links)) {
      const url = new URL(value);
      if (url.origin !== "http://127.0.0.1:4198") continue;
      const response = await request.get(url.pathname);
      expect(response.ok(), value).toBe(true);
      if (url.hash) {
        const html = await response.text();
        expect(html, value).toContain(`id="${url.hash.slice(1)}"`);
      }
    }
    expect(errors).toEqual([]);
  }
});
