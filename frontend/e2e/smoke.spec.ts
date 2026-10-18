import { expect, test } from "@playwright/test";

/**
 * PR 17：页面冒烟 —— 证明 dev server 能起、App 能挂载、主布局可见。
 *
 * 后端不启动：挂载时 HistoryPanel 会拉 /api/tasks，这里桩成空列表，
 * 避免 E2E 依赖真实服务。
 */
test.beforeEach(async ({ page }) => {
  await page.route("**/api/tasks", (route) =>
    route.fulfill({ status: 200, contentType: "application/json", body: "[]" }),
  );
});

test("首页渲染应用标题与新建入口", async ({ page }) => {
  await page.goto("/");

  await expect(page.getByRole("heading", { level: 1 })).toContainText("Looploop");
  await expect(page.getByRole("heading", { level: 1 })).toContainText("噜噜");

  await expect(page.getByText("Start a New Screenplay")).toBeVisible();
  await expect(page.getByRole("button", { name: "Convert" })).toBeVisible();
});

test("文本不足 100 字符时 Convert 按钮禁用", async ({ page }) => {
  await page.goto("/");

  const textarea = page.getByPlaceholder(/paste your novel text/i);
  await textarea.fill("太短");

  await expect(page.getByRole("button", { name: "Convert" })).toBeDisabled();
});
