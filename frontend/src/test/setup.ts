// 把 jest-dom 的断言扩展（toBeInTheDocument / toHaveTextContent …）注册到
// Vitest 的 expect 上。
//
// 采用 import 方式而不是往 tsconfig 的 `types` 里加 "vitest/globals"：
// 测试文件统一用显式 import（`import { describe } from "vitest"`），
// 这样 `tsc -b` 在 include: ["src"] 下就能正常类型检查测试文件，
// 不必往应用的 tsconfig 里注入测试全局。
import "@testing-library/jest-dom/vitest";
