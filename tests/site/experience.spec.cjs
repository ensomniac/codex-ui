const { test, expect } = require("@playwright/test");
const AxeBuilder = require("@axe-core/playwright").default;

for (const width of [320, 390, 768, 1440]) {
  test(`home, tasks and guide remain readable at ${width}px`, async ({ page }) => {
    await page.setViewportSize({ width, height: 900 });
    for (const route of ["/", "/recipes.html", "/guide.html", "/chrome-session.html"]) {
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
test("a visitor can choose a task and copy its complete instructions", async ({ page, context }) => {
  await context.grantPermissions(["clipboard-read", "clipboard-write"]);
  await page.goto("/");
  await page.getByRole("link", { name: "Try it with your agent" }).click();
  await expect(page).toHaveURL(/recipes\.html#first-run$/);
  for (const id of ["first-run", "signed-in", "ui-fix", "workspace"]) {
    const card = page.locator(`#${id}`);
    const task = await card.locator("p[id]").innerText();
    await card.getByRole("button", { name: "Copy task", exact: true }).click();
    expect(await page.evaluate(() => navigator.clipboard.readText())).toBe(task);
    await expect(page.locator("#copy-message")).toHaveText("Task copied.");
  }
});
test("tasks remain selectable when the clipboard is unavailable", async ({ page }) => {
  await page.addInitScript(() => {
    Object.defineProperty(navigator, "clipboard", {
      value: { writeText: async () => { throw new Error("denied"); } },
    });
  });
  await page.goto("/recipes.html");
  await page.locator("#first-run").getByRole("button", { name: "Copy task" }).click();
  expect(await page.evaluate(() => getSelection().toString())).toBe(
    await page.locator("#prompt-first").innerText(),
  );
  await expect(page.locator("#copy-message")).toHaveText("Task selected. Use your copy shortcut.");
});
test("tasks and setup instructions work without JavaScript", async ({ browser }) => {
  const context = await browser.newContext({ javaScriptEnabled: false });
  const page = await context.newPage();
  await page.goto("http://127.0.0.1:4198/recipes.html");
  for (const id of ["prompt-first", "prompt-signed", "prompt-fix", "prompt-workspace"])
    await expect(page.locator(`#${id}`)).toBeVisible();
  await expect(page.getByRole("button", { name: "Copy task" })).toHaveCount(0);
  const response = await context.request.get("http://127.0.0.1:4198/start.md");
  expect(response.ok()).toBe(true);
  expect(await response.text()).toContain("codex-ui press --chrome-url 'codex-ui/?demo=first-run'");
  await context.close();
});
test("internal guide anchors and local assets resolve", async ({
  page,
  request,
}) => {
  for (const route of ["/", "/recipes.html", "/guide.html", "/chrome-session.html"]) {
    const errors = [];
    page.on("pageerror", (error) => errors.push(error.message));
    await page.goto(route);
    const links = await page
      .locator('a[href],img[src],link[rel="stylesheet"],script[src],source[src],track[src],video[poster]')
      .evaluateAll((nodes) =>
        nodes.map((node) => node.href || node.src || node.poster).filter(Boolean),
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

test("Chrome walkthrough is discoverable, playable and gives a complete agent task", async ({ page, context }) => {
  await context.grantPermissions(["clipboard-read", "clipboard-write"]);
  await page.goto("/");
  await page.getByRole("link", { name: "Inspect your existing Chrome session" }).click();
  await expect(page).toHaveURL(/chrome-session\.html$/);
  await page.getByRole("button", { name: "Copy task", exact: true }).click();
  expect(await page.evaluate(() => navigator.clipboard.readText())).toBe(
    await page.locator("#chrome-agent-task").innerText(),
  );
  const video = page.locator("video");
  await video.evaluate((element) => element.play());
  await expect.poll(() => video.evaluate((element) => element.currentTime)).toBeGreaterThan(0.5);
  expect(await video.evaluate((element) => element.duration)).toBeCloseTo(7.167, 1);
  await video.evaluate((element) => element.pause());
  const description = JSON.parse(await page.locator('script[type="application/ld+json"]').textContent());
  expect(description["@type"]).toBe("VideoObject");
  expect(description.contentUrl).toBe("https://ensomniac.github.io/codex-ui/media/native-click.mp4");
  expect(description.duration).toBe("PT7.167S");
  expect(await page.locator('link[rel="canonical"]').getAttribute("href")).toBe(
    "https://ensomniac.github.io/codex-ui/chrome-session.html",
  );
});

test("Chrome walkthrough and video description remain useful without JavaScript", async ({ browser }) => {
  const context = await browser.newContext({ javaScriptEnabled: false });
  const page = await context.newPage();
  await page.goto("http://127.0.0.1:4198/chrome-session.html");
  await expect(page.locator("#chrome-agent-task")).toBeVisible();
  await expect(page.getByRole("button", { name: "Copy task" })).toHaveCount(0);
  await expect(page.locator("video")).toHaveAttribute("controls", "");
  await expect(page.locator("video")).not.toHaveAttribute("autoplay");
  await expect(page.locator("figcaption")).toContainText("one activation");
  await context.close();
});
