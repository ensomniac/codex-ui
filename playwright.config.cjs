const { defineConfig } = require("@playwright/test");
module.exports = defineConfig({
  testDir: "./tests/site",
  fullyParallel: true,
  forbidOnly: !!process.env.CI,
  retries: 0,
  workers: process.env.CI ? 2 : 3,
  reporter: [["list"]],
  use: {
    baseURL: "http://127.0.0.1:4198",
    browserName: "chromium",
    trace: "retain-on-failure",
  },
  webServer: {
    command: "python3 -m http.server 4198 --bind 127.0.0.1 --directory site",
    url: "http://127.0.0.1:4198",
    reuseExistingServer: false,
  },
});
