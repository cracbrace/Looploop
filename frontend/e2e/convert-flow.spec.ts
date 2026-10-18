import path from "node:path";
import { expect, test } from "@playwright/test";

/**
 * PR 17：核心链路 —— 上传文本 → 进度 → 分镜卡片渲染。
 *
 * 全程用 page.route 拦截 /api/**，所以**不需要启动后端**，
 * 也不依赖真实 LLM。这正是「E2E 只验前端集成」的做法。
 */

const TASK_ID = "e2e000000001";

const SCREENPLAY = {
  meta: {
    title: "E2E 测试剧本",
    source: "sample.txt",
    author: "测试",
    genre: "科幻",
    total_scenes: 1,
    total_shots: 2,
    total_duration_estimate: "16s",
    language: "zh-CN",
    version: "0.1.0",
  },
  characters: [
    {
      character_id: "char_000",
      material_id: "C01",
      canonical_name: "叶文洁",
      aliases: [],
      description: "物理学家",
      role_type: "protagonist",
      gender: "female",
      age_range: "25-30",
    },
  ],
  scenes: [
    {
      scene_id: "s01",
      material_id: "S01",
      scene_number: 1,
      location: "红岸基地 · 山顶 · 夜",
      time_of_day: "night",
      atmosphere: "压抑",
      duration_estimate: "16s",
      source_paragraphs: [0, 1],
      shots: [
        {
          shot_id: "s01_01",
          shot_number: 1,
          shot_type: "远景",
          camera_movement: "推进",
          focus_subject: "红岸基地",
          visual_prompt: "Wide shot of an isolated radar base on a snowy ridge at night",
          duration: "8s",
          source_paragraphs: [0],
          extra: {},
        },
        {
          shot_id: "s01_02",
          shot_number: 2,
          shot_type: "特写",
          camera_movement: "固定",
          focus_subject: "叶文洁",
          visual_prompt: "Close-up of a young woman reading a printout under cold light",
          duration: "8s",
          dialogue: {
            character: "叶文洁",
            character_id: "char_000",
            line: "谢谢。",
            emotion: "冷静",
          },
          source_paragraphs: [1],
          extra: {},
        },
      ],
    },
  ],
};

// 两条 SSE 事件：一个中间进度 + 终态 done
const SSE_BODY =
  'data: {"stage":"extracting","message":"正在提取","progress":0.5}\n\n' +
  'data: {"stage":"done","message":"转换完成","progress":1}\n\n';

test("上传文本 → 进度出现 → 分镜卡片渲染", async ({ page }) => {
  await page.route("**/api/tasks", (route) =>
    route.fulfill({ status: 200, contentType: "application/json", body: "[]" }),
  );
  await page.route("**/api/convert", (route) =>
    route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({ task_id: TASK_ID }) }),
  );
  // 故意延迟 400ms，让「加载中」状态可被观察到
  await page.route("**/api/convert/*/stream", async (route) => {
    await new Promise((resolve) => setTimeout(resolve, 400));
    await route.fulfill({
      status: 200,
      contentType: "text/event-stream",
      body: SSE_BODY,
    });
  });
  await page.route("**/api/screenplay/*", (route) =>
    route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(SCREENPLAY) }),
  );

  await page.goto("/");

  // 通过 DropZone 的隐藏 file input 上传（Playwright 支持 hidden input）
  // 注意：本项目是 ESM（"type": "module"），没有 __dirname，用 import.meta.dirname
  await page
    .locator('input[type="file"]')
    .setInputFiles(path.join(import.meta.dirname, "fixtures", "sample.txt"));

  const convert = page.getByRole("button", { name: "Convert" });
  await expect(convert).toBeEnabled();
  await convert.click();

  // 1) 进度状态出现：点 Convert 后 App 切到 LoadingView（按钮随之卸载）。
  //    注意「正在提交...」在 Header 与 LoadingView 各出现一次，
  //    用 getByRole("paragraph") 精确定位到 LoadingView 的那一段，避免 strict 冲突
  await expect(
    page.getByRole("paragraph").filter({ hasText: "正在提交..." }),
  ).toBeVisible();

  // 2) 分镜卡片渲染：fixture 里正好 2 个镜头
  await expect(page.getByText("s01_01")).toBeVisible({ timeout: 15_000 });
  await expect(page.getByText("s01_02")).toBeVisible();

  // 3) 对白也渲染出来了
  await expect(page.getByText("谢谢。")).toBeVisible();
});
