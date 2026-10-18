import { describe, expect, it, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { Sidebar } from "./Sidebar";
import { makeSceneList } from "../test/fixtures";

/**
 * PR 16：`Sidebar` 是场景/角色导航。
 *
 * 说明：计划书提到「角色色块：同一 character_id 两次渲染颜色字符串一致」，
 * 但当前 Sidebar 并没有色块 —— 角色只是一行文本。所以这里按实际实现断言
 * （material_id 回落 + 文案），不虚构色块契约。
 */

function renderSidebar(props: Partial<Parameters<typeof Sidebar>[0]> = {}) {
  const onSelectScene = vi.fn();
  const utils = render(
    <Sidebar
      scenes={makeSceneList(3)}
      characters={[
        { character_id: "char_000", material_id: "C01", canonical_name: "叶文洁" },
        { character_id: "char_001", canonical_name: "雷志成" },
      ]}
      meta={{ total_scenes: 3, total_shots: 7, total_duration_estimate: "1min10s" }}
      totalCharacters={2}
      selectedSceneIndex={0}
      onSelectScene={onSelectScene}
      {...props}
    />,
  );
  return { ...utils, onSelectScene };
}

describe("Sidebar 渲染", () => {
  it("场景条数与 props 一致", () => {
    renderSidebar();

    expect(screen.getByText(/S01 · 地点1/)).toBeInTheDocument();
    expect(screen.getByText(/S02 · 地点2/)).toBeInTheDocument();
    expect(screen.getByText(/S03 · 地点3/)).toBeInTheDocument();
  });

  it("无 material_id 时回落到 scene_id", () => {
    renderSidebar({
      scenes: [{ scene_id: "s09", location: "无名地点" }],
    });

    expect(screen.getByText(/s09 · 无名地点/)).toBeInTheDocument();
  });

  it("渲染角色名，material_id 缺失时回落到 character_id", () => {
    renderSidebar();

    expect(screen.getByText(/C01 叶文洁/)).toBeInTheDocument();
    expect(screen.getByText(/char_001 雷志成/)).toBeInTheDocument();
  });

  it("底部展示场景/镜头/角色/总时长摘要", () => {
    renderSidebar();

    expect(screen.getByText("3 scenes")).toBeInTheDocument();
    expect(screen.getByText("7 shots")).toBeInTheDocument();
    expect(screen.getByText("2 characters")).toBeInTheDocument();
    expect(screen.getByText("1min10s")).toBeInTheDocument();
  });
});

describe("Sidebar 交互", () => {
  it("点击第 3 个场景传入索引 2（不是 scene 对象）", async () => {
    const user = userEvent.setup();
    const { onSelectScene } = renderSidebar();

    await user.click(screen.getByText(/S03 · 地点3/));

    expect(onSelectScene).toHaveBeenCalledWith(2);
  });

  it("当前选中场景带高亮 class，其它不带", () => {
    renderSidebar({ selectedSceneIndex: 1 });

    expect(screen.getByText(/S02 · 地点2/)).toHaveClass("bg-zinc-800");
    expect(screen.getByText(/S01 · 地点1/)).not.toHaveClass("bg-zinc-800");
  });
});
