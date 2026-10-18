import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, render, screen, waitFor } from "@testing-library/react";
import App from "./App";

/**
 * PR 13 的 smoke：只证明「组件树能挂载 + 主布局可见」。
 * 真正的交互断言留给 PR 14-16（client / hook / 组件）。
 */

// App 挂载时 HistoryPanel 会拉历史列表，必须桩掉 fetch，否则会打真实网络
let fetchMock: ReturnType<typeof vi.fn>;

beforeEach(() => {
  fetchMock = vi.fn(
    async () =>
      new Response(JSON.stringify([]), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      }),
  );
  vi.stubGlobal("fetch", fetchMock);
});

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

/**
 * 渲染并等挂载副作用落地。
 *
 * 必须等待：HistoryPanel 的 fetch 是异步的，若测试在它 resolve 前就结束，
 * React 的 setState 会落在 act() 之外，控制台刷出
 * "An update to HistoryPanel inside a test was not wrapped in act(...)"。
 * 那类警告会淹没真正的失败信息，所以在这里一次性收敛。
 */
async function renderApp() {
  render(<App />);
  await waitFor(() => expect(fetchMock).toHaveBeenCalled());
}

describe("<App /> 冒烟", () => {
  it("挂载后渲染应用标题", async () => {
    await renderApp();

    const heading = screen.getByRole("heading", { level: 1 });

    expect(heading).toHaveTextContent(/Looploop/);
    expect(heading).toHaveTextContent("噜噜");
  });

  it("首屏显示新建剧本入口", async () => {
    await renderApp();

    expect(screen.getByText("Start a New Screenplay")).toBeInTheDocument();
    expect(screen.getByPlaceholderText(/paste your novel text/i)).toBeInTheDocument();
  });

  it("挂载副作用确实执行（历史列表被拉取）", async () => {
    await renderApp();

    expect(fetchMock).toHaveBeenCalledTimes(1);
  });
});
