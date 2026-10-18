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
  },
});
