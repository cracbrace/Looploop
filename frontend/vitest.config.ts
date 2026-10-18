import { defineConfig } from "vitest/config";
import react from "@vitejs/plugin-react";

// 独立的 Vitest 配置，**不修改 vite.config.ts** —— 测试的关注点（jsdom、
// setupFiles、include 范围）不该和生产构建配置混在一个文件里。
// 这里只挂 react 插件：jsdom 环境不需要 tailwind，省掉它也能加快启动。
export default defineConfig({
  plugins: [react()],
  test: {
    environment: "jsdom",
    globals: true,
    setupFiles: ["./src/test/setup.ts"],
    include: ["src/**/*.{test,spec}.{ts,tsx}"],
    // 每个用例后还原 spy/stub，避免跨用例泄漏
    restoreMocks: true,
    coverage: {
      provider: "v8",
      reporter: ["text", "lcov"],
      include: ["src/**/*.{ts,tsx}"],
      // 排除范围只放「非被测代码」：
      //   测试自身（*.test.*）、测试基建（src/test/）、入口（main.tsx）、
      //   纯类型声明（types/，没有可执行语句）
      exclude: [
        "src/**/*.{test,spec}.{ts,tsx}",
        "src/test/**",
        "src/main.tsx",
        "src/types/**",
      ],
      // 阈值：实测基线 47.09 / 33.67 / 35.5 / 53.7（排除范围生效后），
      // 各留约 2 个百分点余量 —— 目的是挡住「覆盖率回退」，不是追求高分。
      // 注意：阈值在 `npm test`（全量）时生效；单文件调试请用 --coverage=false。
      thresholds: {
        statements: 45,
        branches: 32,
        functions: 33,
        lines: 51,
      },
    },
  },
});
