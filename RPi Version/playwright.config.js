const {defineConfig, devices} = require("@playwright/test");

const externalBaseUrl = process.env.PHYTO_UI_BASE_URL;

module.exports = defineConfig({
  testDir: "./tests/ui",
  outputDir: "/tmp/phyto-playwright-results",
  timeout: 20_000,
  forbidOnly: true,
  retries: 0,
  reporter: "line",
  use: {
    baseURL: externalBaseUrl || "http://127.0.0.1:38123",
    locale: "fr-FR",
    serviceWorkers: "block",
    trace: "retain-on-failure",
  },
  projects: [
    {name: "desktop-chromium", use: {...devices["Desktop Chrome"]}},
    {name: "mobile-chromium", use: {...devices["Pixel 5"]}},
    {name: "mobile-etroit", use: {viewport: {width: 320, height: 568}, isMobile: true, hasTouch: true}},
    {name: "mobile-paysage", use: {viewport: {width: 568, height: 320}, isMobile: true, hasTouch: true}},
    {name: "pwa-chromium", use: {...devices["Pixel 5"], serviceWorkers: "allow"}},
  ],
  webServer: externalBaseUrl ? undefined : {
    command: `${process.env.PHYTO_TEST_PYTHON || "python3"} tests/ui_server.py`,
    port: 38123,
    reuseExistingServer: false,
    timeout: 20_000,
  },
});
