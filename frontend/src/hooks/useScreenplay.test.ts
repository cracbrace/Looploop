import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { act, renderHook } from "@testing-library/react";
import { useScreenplay } from "./useScreenplay";
import * as api from "../api/client";
import type { PipelineStage, Screenplay, Shot } from "../types/screenplay";

/**
 * PR 15：`useScreenplay` 是前端状态中枢。
 * 用模块级 mock 替掉整个 API 层（比 stub fetch 更高层、更快）。
 */

vi.mock("../api/client");

const mockApi = vi.mocked(api);

function makeShot(overrides: Partial<Shot> = {}): Shot {
  return {
    shot_id: "s01_01",
    shot_number: 1,
    shot_type: "特写",
    camera_movement: "推进",
    focus_subject: "叶文洁",
    visual_prompt: "Close-up of a young woman reading a printout, 1969, cinematic",
    duration: "8s",
    source_paragraphs: [0],
    extra: {},
    ...overrides,
  };
}

/** 两场戏、第一场两个镜头 —— 用于验证「局部更新不动其他镜头/场景」 */
function makeScreenplay(): Screenplay {
  return {
    meta: {
      title: "原始标题",
      source: "测试",
      author: "测试",
      genre: "科幻",
      total_scenes: 2,
      total_shots: 3,
      total_duration_estimate: "24s",
      language: "zh-CN",
      version: "0.1.0",
    },
    characters: [],
    scenes: [
      {
        scene_id: "s01",
        scene_number: 1,
        location: "红岸基地",
        time_of_day: "night",
        atmosphere: "孤独",
        duration_estimate: "16s",
        source_paragraphs: [0],
        shots: [
          makeShot({ shot_id: "s01_01", shot_number: 1 }),
          makeShot({ shot_id: "s01_02", shot_number: 2, shot_type: "远景" }),
        ],
      },
      {
        scene_id: "s02",
        scene_number: 2,
        location: "控制室",
        time_of_day: "night",
        atmosphere: "紧张",
        duration_estimate: "8s",
        source_paragraphs: [1],
        shots: [makeShot({ shot_id: "s02_01", shot_number: 1, shot_type: "中景" })],
      },
    ],
  };
}

/** 捕获传给 streamProgress 的三个回调，供用例手动触发 */
type StreamHandlers = {
  onStage: (s: PipelineStage) => void;
  onDone: () => void | Promise<void>;
  onError: (msg: string) => void;
};

function captureStream(): StreamHandlers {
  const handlers = {} as StreamHandlers;
  mockApi.streamProgress.mockImplementation((_id, onStage, onDone, onError) => {
    handlers.onStage = onStage;
    handlers.onDone = onDone;
    handlers.onError = onError;
    return new AbortController();
  });
  return handlers;
}

beforeEach(() => {
  vi.clearAllMocks();
  mockApi.convertNovel.mockResolvedValue("task-1");
  mockApi.getScreenplay.mockResolvedValue(makeScreenplay());
  mockApi.regenerateShot.mockResolvedValue(makeShot({ shot_type: "大特写" }));
});

afterEach(() => {
  vi.clearAllMocks();
});

// ============================================================
// 初始状态
// ============================================================

describe("初始状态", () => {
  it("status=idle、screenplay=null、选中项归零", () => {
    const { result } = renderHook(() => useScreenplay());

    expect(result.current.status).toBe("idle");
    expect(result.current.screenplay).toBeNull();
    expect(result.current.taskId).toBeNull();
    expect(result.current.progress).toBe(0);
    expect(result.current.selectedSceneIndex).toBe(0);
    expect(result.current.selectedShotId).toBeNull();
    expect(result.current.originalText).toBe("");
    expect(result.current.paragraphs).toEqual([]);
    expect(result.current.canUndo()).toBe(false);
    expect(result.current.canRedo()).toBe(false);
  });
});

// ============================================================
// startConvert：成功链
// ============================================================

describe("startConvert 成功链", () => {
  it("提交后进入 running，taskId 与流都已就绪", async () => {
    const handlers = captureStream();
    const { result } = renderHook(() => useScreenplay());

    await act(async () => {
      await result.current.startConvert("一段足够长的小说正文");
    });

    expect(mockApi.convertNovel).toHaveBeenCalledWith("一段足够长的小说正文");
    expect(result.current.taskId).toBe("task-1");
    expect(result.current.status).toBe("running");
    expect(handlers.onStage).toBeTypeOf("function");
  });

  it("按舞台事件更新 status / progress / message", async () => {
    const handlers = captureStream();
    const { result } = renderHook(() => useScreenplay());
    await act(async () => {
      await result.current.startConvert("正文");
    });

    act(() => {
      handlers.onStage({ stage: "extracting", message: "正在提取", progress: 0.4 });
    });

    expect(result.current.status).toBe("extracting");
    expect(result.current.progress).toBe(0.4);
    expect(result.current.progressMessage).toBe("正在提取");
  });

  it("done 时拉取剧本并置为 done", async () => {
    const handlers = captureStream();
    const screenplay = makeScreenplay();
    mockApi.getScreenplay.mockResolvedValueOnce(screenplay);
    const { result } = renderHook(() => useScreenplay());
    await act(async () => {
      await result.current.startConvert("正文");
    });

    await act(async () => {
      await handlers.onDone();
    });

    expect(mockApi.getScreenplay).toHaveBeenCalledWith("task-1");
    expect(result.current.screenplay).toEqual(screenplay);
    expect(result.current.status).toBe("done");
    expect(result.current.selectedSceneIndex).toBe(0);
  });

  it("done 后拉取失败 → status=error 并给出固定文案", async () => {
    const handlers = captureStream();
    mockApi.getScreenplay.mockRejectedValueOnce(new Error("boom"));
    const { result } = renderHook(() => useScreenplay());
    await act(async () => {
      await result.current.startConvert("正文");
    });

    await act(async () => {
      await handlers.onDone();
    });

    expect(result.current.status).toBe("error");
    expect(result.current.progressMessage).toBe("获取剧本失败");
  });
});

// ============================================================
// startConvert：失败链与文本归一化
// ============================================================

describe("startConvert 失败链", () => {
  it("convertNovel 拒绝 → status=error", async () => {
    mockApi.convertNovel.mockRejectedValueOnce(new Error("转换失败：网络错误"));
    const { result } = renderHook(() => useScreenplay());

    await act(async () => {
      await result.current.startConvert("正文");
    });

    expect(result.current.status).toBe("error");
    expect(result.current.progressMessage).toBe("转换失败：网络错误");
  });

  it("流回调报错 → status=error，保留后端消息", async () => {
    const handlers = captureStream();
    const { result } = renderHook(() => useScreenplay());
    await act(async () => {
      await result.current.startConvert("正文");
    });

    act(() => {
      handlers.onError("管线崩溃");
    });

    expect(result.current.status).toBe("error");
    expect(result.current.progressMessage).toBe("管线崩溃");
  });

  it("把内联章节标记规范成独立段落（与后端 text_splitter 对齐）", async () => {
    captureStream();
    const { result } = renderHook(() => useScreenplay());

    await act(async () => {
      await result.current.startConvert("正文一。第二章 标题");
    });

    expect(result.current.originalText).toContain("\n\n第二章");
    expect(result.current.paragraphs).toHaveLength(2);
  });
});

// ============================================================
// cancelConvert / reset
// ============================================================

describe("cancelConvert 与 reset", () => {
  it("cancelConvert 中止流并回到 idle", async () => {
    const controller = new AbortController();
    const abortSpy = vi.spyOn(controller, "abort");
    mockApi.streamProgress.mockReturnValue(controller);
    const { result } = renderHook(() => useScreenplay());
    await act(async () => {
      await result.current.startConvert("正文");
    });

    act(() => {
      result.current.cancelConvert();
    });

    expect(abortSpy).toHaveBeenCalled();
    expect(result.current.status).toBe("idle");
  });

  it("reset 清空全部状态", async () => {
    const handlers = captureStream();
    const { result } = renderHook(() => useScreenplay());
    await act(async () => {
      await result.current.startConvert("正文");
    });
    await act(async () => {
      await handlers.onDone();
    });

    act(() => {
      result.current.reset();
    });

    expect(result.current.screenplay).toBeNull();
    expect(result.current.taskId).toBeNull();
    expect(result.current.status).toBe("idle");
    expect(result.current.progress).toBe(0);
  });
});

// ============================================================
// loadFromHistory
// ============================================================

describe("loadFromHistory", () => {
  it("加载成功后 status=done、progress=1", async () => {
    const { result } = renderHook(() => useScreenplay());

    await act(async () => {
      await result.current.loadFromHistory("t1");
    });

    expect(result.current.taskId).toBe("t1");
    expect(result.current.status).toBe("done");
    expect(result.current.progress).toBe(1);
    expect(result.current.screenplay?.meta.title).toBe("原始标题");
  });

  it("带 _original_text 时恢复原文并删除内部字段", async () => {
    const withText = { ...makeScreenplay(), _original_text: "第一段。\n\n第二段。" };
    mockApi.getScreenplay.mockResolvedValueOnce(withText);
    const { result } = renderHook(() => useScreenplay());

    await act(async () => {
      await result.current.loadFromHistory("t1");
    });

    expect(result.current.originalText).toBe("第一段。\n\n第二段。");
    expect(result.current.paragraphs).toEqual(["第一段。", "第二段。"]);
    expect(result.current.screenplay).not.toHaveProperty("_original_text");
  });

  it("返回空数据 → status=error", async () => {
    mockApi.getScreenplay.mockResolvedValueOnce({} as Screenplay);
    const { result } = renderHook(() => useScreenplay());

    await act(async () => {
      await result.current.loadFromHistory("t1");
    });

    expect(result.current.status).toBe("error");
    expect(result.current.progressMessage).toBe("Screenplay data is empty or invalid");
  });

  it("拉取失败 → status=error", async () => {
    mockApi.getScreenplay.mockRejectedValueOnce(new Error("404"));
    const { result } = renderHook(() => useScreenplay());

    await act(async () => {
      await result.current.loadFromHistory("nope");
    });

    expect(result.current.status).toBe("error");
    expect(result.current.progressMessage).toBe("404");
  });
});

// ============================================================
// updateScreenplay / undo / redo
// ============================================================

describe("updateScreenplay 与撤销重做", () => {
  async function loadHook() {
    const { result } = renderHook(() => useScreenplay());
    await act(async () => {
      await result.current.loadFromHistory("t1");
    });
    return result;
  }

  it("更新后 canUndo 为真，undo 回到旧值，redo 再前进", async () => {
    const result = await loadHook();

    act(() => {
      result.current.updateScreenplay((prev: Screenplay) => ({
        ...prev,
        meta: { ...prev.meta, title: "改过的标题" },
      }));
    });
    expect(result.current.screenplay?.meta.title).toBe("改过的标题");
    expect(result.current.canUndo()).toBe(true);

    act(() => {
      result.current.undo();
    });
    expect(result.current.screenplay?.meta.title).toBe("原始标题");
    expect(result.current.canRedo()).toBe(true);

    act(() => {
      result.current.redo();
    });
    expect(result.current.screenplay?.meta.title).toBe("改过的标题");
  });

  it("pushUndo=false 时不入栈", async () => {
    const result = await loadHook();

    act(() => {
      result.current.updateScreenplay(
        (prev: Screenplay) => ({ ...prev, meta: { ...prev.meta, title: "静默改动" } }),
        false,
      );
    });

    expect(result.current.canUndo()).toBe(false);
  });

  it("新的改动会清空 redo 栈", async () => {
    const result = await loadHook();
    act(() => {
      result.current.updateScreenplay((prev: Screenplay) => ({
        ...prev,
        meta: { ...prev.meta, title: "A" },
      }));
    });
    act(() => {
      result.current.undo();
    });
    expect(result.current.canRedo()).toBe(true);

    act(() => {
      result.current.updateScreenplay((prev: Screenplay) => ({
        ...prev,
        meta: { ...prev.meta, title: "B" },
      }));
    });

    expect(result.current.canRedo()).toBe(false);
  });
});

// ============================================================
// handleRegenerateShot（局部更新语义）
// ============================================================

describe("handleRegenerateShot", () => {
  async function loadHook() {
    const { result } = renderHook(() => useScreenplay());
    await act(async () => {
      await result.current.loadFromHistory("t1");
    });
    return result;
  }

  it("只替换目标镜头，同场景其他镜头与其它场景保持不变", async () => {
    const result = await loadHook();
    const before = result.current.screenplay!;

    await act(async () => {
      await result.current.handleRegenerateShot("s01", "s01_01", "压低机位");
    });

    const after = result.current.screenplay!;

    expect(mockApi.regenerateShot).toHaveBeenCalledWith(
      "s01", "s01_01", expect.anything(), "压低机位",
    );
    expect(after.scenes[0].shots[0].shot_type).toBe("大特写");
    expect(after.scenes[0].shots[1]).toEqual(before.scenes[0].shots[1]);
    expect(after.scenes[1]).toEqual(before.scenes[1]);
  });

  it("screenplay 为空时直接返回，不调接口", async () => {
    const { result } = renderHook(() => useScreenplay());

    await act(async () => {
      await result.current.handleRegenerateShot("s01", "s01_01");
    });

    expect(mockApi.regenerateShot).not.toHaveBeenCalled();
  });

  it("重刷失败时只打日志，不改状态", async () => {
    const result = await loadHook();
    const before = result.current.screenplay!;
    const errSpy = vi.spyOn(console, "error").mockImplementation(() => {});
    mockApi.regenerateShot.mockRejectedValueOnce(new Error("500"));

    await act(async () => {
      await result.current.handleRegenerateShot("s01", "s01_01");
    });

    expect(result.current.screenplay).toEqual(before);
    expect(result.current.status).toBe("done");
    expect(errSpy).toHaveBeenCalled();
    errSpy.mockRestore();
  });

  it("选中态 setter 生效且不影响剧本数据", async () => {
    const result = await loadHook();
    const before = result.current.screenplay;

    act(() => {
      result.current.setSelectedSceneIndex(1);
      result.current.setSelectedShotId("s02_01");
      result.current.setSelectedCharacterId("char_000");
    });

    expect(result.current.selectedSceneIndex).toBe(1);
    expect(result.current.selectedShotId).toBe("s02_01");
    expect(result.current.selectedCharacterId).toBe("char_000");
    expect(result.current.screenplay).toBe(before);
  });
});
