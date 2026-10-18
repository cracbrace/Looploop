// 把 jest-dom 的断言扩展（toBeInTheDocument / toHaveTextContent …）注册到
// Vitest 的 expect 上。
//
// 采用 import 方式而不是往 tsconfig 的 `types` 里加 "vitest/globals"：
// 测试文件统一用显式 import（`import { describe } from "vitest"`），
// 这样 `tsc -b` 在 include: ["src"] 下就能正常类型检查测试文件，
// 不必往应用的 tsconfig 里注入测试全局。
import "@testing-library/jest-dom/vitest";

// jsdom 不实现 ResizeObserver，而 SourcePanel 用它做自适应字号。
// 这里给个空实现，避免组件在测试环境里直接抛错。
// （空实现即可：本项目的测试都不依赖真实尺寸变化。）
if (!("ResizeObserver" in globalThis)) {
  class ResizeObserverStub {
    observe() {}
    unobserve() {}
    disconnect() {}
  }
  (globalThis as unknown as { ResizeObserver: unknown }).ResizeObserver =
    ResizeObserverStub;
}
