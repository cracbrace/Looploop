import { describe, expect, it, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { ShotCard } from "./ShotCard";
import { makeShot, makeShotWithDialogue } from "../test/fixtures";

/**
 * PR 16：`ShotCard` 是分镜主视图的核心交互单元。
 * 覆盖：字段渲染、无对白占位、点击选中、选中态、重刷面板、双击内联编辑。
 */

function renderCard(props: Partial<Parameters<typeof ShotCard>[0]> = {}) {
  const onClick = vi.fn();
  const onEdit = vi.fn();
  const utils = render(
    <ShotCard
      shot={makeShotWithDialogue()}
      shotIndex={0}
      isSelected={false}
      onClick={onClick}
      onEdit={onEdit}
      {...props}
    />,
  );
  return { ...utils, onClick, onEdit };
}

describe("ShotCard 渲染", () => {
  it("渲染镜头 ID、景别、运镜、焦点、时长与 prompt", () => {
    renderCard();

    expect(screen.getByText("s01_01")).toBeInTheDocument();
    expect(screen.getByText("特写")).toBeInTheDocument();
    // 运镜文案出现两次：徽标本身 + CameraTooltip 的悬浮气泡
    const movements = screen.getAllByText("推进");
    expect(movements).toHaveLength(2);
    expect(movements[0]).toHaveClass("cursor-help");
    expect(screen.getByText("Focus: 叶文洁")).toBeInTheDocument();
    expect(screen.getByText("8s")).toBeInTheDocument();
    expect(screen.getByText(/prompt: Close-up of a young woman/)).toBeInTheDocument();
  });

  it("有对白时渲染角色、情绪与台词", () => {
    renderCard();

    expect(screen.getByText("叶文洁")).toBeInTheDocument();
    expect(screen.getByText("冷静")).toBeInTheDocument();
    expect(screen.getByText("谢谢。")).toBeInTheDocument();
    expect(screen.queryByText("No dialogue")).not.toBeInTheDocument();
  });

  it("无对白时显示占位文案", () => {
    // 注意：`Shot.dialogue` 的类型是 `Dialogue | undefined`，不含 null，
    // 所以这里用 undefined（`satisfies` 的 fixture 让这个错误在 build 时就被抓到）
    renderCard({ shot: makeShot({ dialogue: undefined }) });

    expect(screen.getByText("No dialogue")).toBeInTheDocument();
  });
});

describe("ShotCard 交互", () => {
  it("点击卡片触发 onClick", async () => {
    const user = userEvent.setup();
    const { onClick } = renderCard();

    await user.click(screen.getByText("s01_01"));

    expect(onClick).toHaveBeenCalledTimes(1);
  });

  it("isSelected 为真时挂上选中态 class", () => {
    const { container, unmount } = renderCard({ isSelected: true });
    expect(container.firstElementChild).toHaveClass("ring-emerald-500/50");
    unmount();

    const { container: plain } = renderCard({ isSelected: false });
    expect(plain.firstElementChild).not.toHaveClass("ring-emerald-500/50");
  });

  it("双击时长进入内联编辑，回车保存回调 onEdit", async () => {
    const user = userEvent.setup();
    const { onEdit } = renderCard();

    await user.dblClick(screen.getByText("8s"));

    const input = screen.getByDisplayValue("8s");
    await user.clear(input);
    await user.type(input, "12s{Enter}");

    expect(onEdit).toHaveBeenCalledWith("duration", "12s");
  });

  it("值未改变时回车不触发 onEdit", async () => {
    const user = userEvent.setup();
    const { onEdit } = renderCard();

    await user.dblClick(screen.getByText("8s"));
    await user.type(screen.getByDisplayValue("8s"), "{Enter}");

    expect(onEdit).not.toHaveBeenCalled();
  });
});

describe("ShotCard 重刷入口", () => {
  it("未传 onRegenerate 时不渲染重刷按钮", () => {
    renderCard();

    expect(screen.queryByTitle("Regenerate this shot")).not.toBeInTheDocument();
  });

  it("点击 ↻ 展开反馈框，提交时把反馈传给 onRegenerate", async () => {
    const user = userEvent.setup();
    const onRegenerate = vi.fn().mockResolvedValue(undefined);
    renderCard({ onRegenerate });

    await user.click(screen.getByTitle("Regenerate this shot"));
    const feedback = screen.getByPlaceholderText(/What to change/);
    await user.type(feedback, "压低机位");
    await user.click(screen.getByText("Regenerate"));

    expect(onRegenerate).toHaveBeenCalledWith("压低机位");
  });

  it("未填反馈时传 undefined（让后端用默认提示）", async () => {
    const user = userEvent.setup();
    const onRegenerate = vi.fn().mockResolvedValue(undefined);
    renderCard({ onRegenerate });

    await user.click(screen.getByTitle("Regenerate this shot"));
    await user.click(screen.getByText("Regenerate"));

    expect(onRegenerate).toHaveBeenCalledWith(undefined);
  });

  it("展开重刷面板不会冒泡触发卡片 onClick", async () => {
    const user = userEvent.setup();
    const onRegenerate = vi.fn().mockResolvedValue(undefined);
    const { onClick } = renderCard({ onRegenerate });

    await user.click(screen.getByTitle("Regenerate this shot"));

    expect(onClick).not.toHaveBeenCalled();
  });
});
