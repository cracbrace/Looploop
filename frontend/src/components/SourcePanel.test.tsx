import { describe, expect, it, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { SourcePanel } from "./SourcePanel";

/**
 * PR 16：`SourcePanel` 是原文对照面板。
 *
 * 说明：计划书提到「点击标题栏 → 展开/收起状态切换（aria-expanded）」，
 * 但当前实现的展开/收起由父组件通过 `visible` 控制，面板内部没有折叠开关。
 * 所以这里断言实际契约：visible=false 的占位态、visible=true 的渲染、
 * 高亮、截断、关闭回调。
 */

const PARAGRAPHS = [
  "第一段：1969年冬，大兴安岭的暴风雪下了整整三天。",
  "第二段：叶文洁裹紧军大衣，推开铁门。",
  "第三段：寒风如刀，灌入领口。",
];

function renderPanel(props: Partial<Parameters<typeof SourcePanel>[0]> = {}) {
  const onClose = vi.fn();
  const utils = render(
    <SourcePanel
      paragraphs={PARAGRAPHS}
      highlightedParagraphs={[]}
      onClose={onClose}
      visible
      {...props}
    />,
  );
  return { ...utils, onClose };
}

describe("SourcePanel 占位态", () => {
  it("visible=false 时显示提示文案，不渲染段落", () => {
    renderPanel({ visible: false });

    expect(screen.getByText("Click a shot card to view source text")).toBeInTheDocument();
    expect(screen.queryByText(/第一段/)).not.toBeInTheDocument();
  });

  it("可见但无原文时显示 Original text not available", () => {
    renderPanel({ paragraphs: [] });

    expect(screen.getByText("Original text not available")).toBeInTheDocument();
  });
});

describe("SourcePanel 渲染", () => {
  it("逐段渲染，并带上 0-based 段落序号", () => {
    renderPanel();

    expect(screen.getByText(/第一段/)).toBeInTheDocument();
    expect(screen.getByText(/第二段/)).toBeInTheDocument();
    expect(screen.getByText(/第三段/)).toBeInTheDocument();
    // 序号是独立 span
    expect(screen.getByText("0")).toBeInTheDocument();
    expect(screen.getByText("2")).toBeInTheDocument();
  });

  it("超长段落截断到 300 字符并加省略号", () => {
    const long = "甲".repeat(400);
    renderPanel({ paragraphs: [long] });

    const paragraph = screen.getByText(/甲/);
    expect(paragraph.textContent).toContain("...");
    // 400 个甲被截到 300，因此不会出现完整的 400
    expect(paragraph.textContent).not.toContain("甲".repeat(301));
  });
});

describe("SourcePanel 高亮", () => {
  it("被高亮的段落带琥珀色背景 class，其它不带", () => {
    renderPanel({ highlightedParagraphs: [1] });

    expect(screen.getByText(/第二段/)).toHaveClass("bg-amber-500/10");
    expect(screen.getByText(/第一段/)).not.toHaveClass("bg-amber-500/10");
  });

  it("有高亮时标题栏展示段落序号列表", () => {
    renderPanel({ highlightedParagraphs: [0, 2] });

    expect(screen.getByText("¶ 0, 2")).toBeInTheDocument();
  });

  it("无高亮时不展示序号列表", () => {
    renderPanel({ highlightedParagraphs: [] });

    expect(screen.queryByText(/¶/)).not.toBeInTheDocument();
  });
});

describe("SourcePanel 交互", () => {
  it("点击 Close 触发 onClose", async () => {
    const user = userEvent.setup();
    const { onClose } = renderPanel();

    await user.click(screen.getByText("Close"));

    expect(onClose).toHaveBeenCalledTimes(1);
  });
});
