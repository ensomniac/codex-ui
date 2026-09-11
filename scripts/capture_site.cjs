// Review artifacts only. Native desktop verification is a separate step.
const { chromium } = require("playwright");
const { mkdirSync } = require("node:fs");
const { resolve } = require("node:path");
const { pathToFileURL } = require("node:url");
(async () => {
  const browser = await chromium.launch();
  const root = resolve(__dirname, "..");
  const output = resolve(root, "test-results/visual");
  mkdirSync(output, { recursive: true });
  try {
    for (const width of [390, 1440]) {
      const page = await browser.newPage({
        viewport: { width, height: 1000 },
        deviceScaleFactor: 1,
      });
      for (const name of ["index", "guide"]) {
        await page.goto(pathToFileURL(resolve(root, `site/${name}.html`)).href);
        await page.screenshot({
          path: resolve(output, `${name}-${width}.png`),
          fullPage: true,
        });
        await page.screenshot({
          path: resolve(output, `${name}-${width}-top.png`),
        });
        if (name === "index") {
          for (const section of [
            "install-section",
            "agents-section",
            "story-section",
            "details-section",
          ]) {
            await page
              .locator("." + section)
              .screenshot({ path: resolve(output, `${section}-${width}.png`) });
          }
        }
      }
      await page.goto(
        pathToFileURL(resolve(root, "examples/playground.html")).href,
      );
      await page.screenshot({
        path: resolve(output, `playground-${width}.png`),
        fullPage: true,
      });
      await page.close();
    }
    const brand = await browser.newPage({
      viewport: { width: 1200, height: 630 },
      deviceScaleFactor: 1,
    });
    await brand.goto(pathToFileURL(resolve(root, "site/social.svg")).href);
    await brand.screenshot({ path: resolve(root, "site/social.png") });
    console.log(
      `Wrote review captures to ${output} and the social preview to site/social.png`,
    );
  } finally {
    await browser.close();
  }
})().catch((error) => {
  console.error(error);
  process.exitCode = 1;
});
