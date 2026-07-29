import path from "node:path";
import { defineConfig, devices } from "@playwright/test";


const artifacts = path.resolve(__dirname, "../output/playwright");
const browserChannel = process.env.E2E_BROWSER_CHANNEL;

export default defineConfig({
  testDir: "./e2e",
  outputDir: path.join(artifacts, "artifacts"),
  timeout: 180_000,
  expect: { timeout: 20_000 },
  fullyParallel: false,
  workers: 1,
  retries: 0,
  reporter: [
    ["list"],
    ["json", { outputFile: path.join(artifacts, "results.json") }],
    ["html", { outputFolder: path.join(artifacts, "html"), open: "never" }],
  ],
  use: {
    baseURL: process.env.E2E_FRONTEND_URL || "http://127.0.0.1:13000",
    trace: "retain-on-failure",
    screenshot: "only-on-failure",
    video: "off",
  },
  projects: [
    {
      name: browserChannel || "chromium",
      use: {
        ...devices["Desktop Chrome"],
        ...(browserChannel ? { channel: browserChannel } : {}),
      },
    },
  ],
});
