import { defineConfig, devices } from "@playwright/test";

// E2E 不依赖真实后端：所有 /api/** 由 page.route 拦截并回 fixture（见 e2e/*.spec.ts）。
// webServer 只负责把前端 dev server 拉起来。
//
// 单独放一个 playwright.config.ts，不碰 vite.config.ts —— 与 vitest.config.ts 同样的原则。
export default defineConfig({
  testDir: "./e2e",
  fullyParallel: false,
  forbidOnly: !!process.env.CI,
  retries: process.env.CI ? 1 : 0,
  reporter: [["list"]],
  use: {
    baseURL: "http://localhost:5173",
    trace: "on-first-retry",
  },
  projects: [
    { name: "chromium", use: { ...devices["Desktop Chrome"] } },
  ],
  webServer: {
    command: "npm run dev -- --port 5173 --strictPort",
    url: "http://localhost:5173",
    reuseExistingServer: !process.env.CI,
    timeout: 120_000,
  },
});
