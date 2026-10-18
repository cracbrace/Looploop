import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import {
  convertNovel,
  deleteTask,
  fetchHistory,
  getManifestUrl,
  getScreenplay,
  getWordUrl,
  getYamlUrl,
  getZipUrl,
  regenerateShot,
  renameTask,
  saveScreenplay,
  streamProgress,
} from "./client";
import type { PipelineStage, Screenplay, Shot } from "../types/screenplay";

/**
 * PR 14：`api/client.ts` 是前端所有网络请求的收口，纯逻辑、最易单测。
 * 全部用 mock fetch，不碰真实后端。
 */

let fetchMock: ReturnType<typeof vi.fn>;

function jsonResponse(body: unknown, status = 200, statusText = "OK") {
  return new Response(JSON.stringify(body), {
    status,
    statusText,
    headers: { "Content-Type": "application/json" },
  });
}

/** 造一个能通过 Screenplay 类型的完整镜头 */
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

/** 造一个最小合法剧本 */
function makeScreenplay(): Screenplay {
  return {
    meta: {
      title: "测试剧本",
      source: "测试",
      author: "测试",
      genre: "科幻",
      total_scenes: 1,
      total_shots: 1,
      total_duration_estimate: "8s",
      language: "zh-CN",
      version: "0.1.0",
    },
    characters: [
      {
        character_id: "char_000",
        canonical_name: "叶文洁",
        aliases: ["小叶"],
        description: "物理学家",
        role_type: "protagonist",
        gender: "female",
        age_range: "25-30",
      },
    ],
    scenes: [
      {
        scene_id: "s01",
        scene_number: 1,
        location: "红岸基地",
        time_of_day: "night",
        atmosphere: "孤独",
        duration_estimate: "8s",
        source_paragraphs: [0],
        shots: [makeShot()],
      },
    ],
  };
}

/** 造一个能按行读的 SSE 响应 */
function sseResponse(chunks: string[]): Response {
  const encoder = new TextEncoder();
  const body = new ReadableStream<Uint8Array>({
    start(controller) {
      for (const chunk of chunks) controller.enqueue(encoder.encode(chunk));
      controller.close();
    },
  });
  return new Response(body, {
    status: 200,
    headers: { "Content-Type": "text/event-stream" },
  });
}

beforeEach(() => {
  fetchMock = vi.fn();
  vi.stubGlobal("fetch", fetchMock);
});

afterEach(() => {
  vi.unstubAllGlobals();
});

// ============================================================
// convertNovel
// ============================================================

describe("convertNovel", () => {
  it("提交到 /api/convert 并返回 task_id", async () => {
    fetchMock.mockResolvedValueOnce(jsonResponse({ task_id: "abc123def456" }));

    const taskId = await convertNovel("一段足够长的小说文本");

    expect(taskId).toBe("abc123def456");
    expect(fetchMock).toHaveBeenCalledTimes(1);
    expect(fetchMock).toHaveBeenCalledWith("/api/convert", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ text: "一段足够长的小说文本" }),
    });
  });

  it("把 meta 合并进请求体", async () => {
    fetchMock.mockResolvedValueOnce(jsonResponse({ task_id: "t1" }));

    await convertNovel("正文", { title: "三体", genre: "科幻" });

    const body = JSON.parse(fetchMock.mock.calls[0][1].body as string);
    expect(body).toEqual({ text: "正文", title: "三体", genre: "科幻" });
  });

  it("非 2xx 时抛出并带上状态文案", async () => {
    fetchMock.mockResolvedValueOnce(jsonResponse({}, 422, "Unprocessable Entity"));

    await expect(convertNovel("正文")).rejects.toThrow(/Convert failed: Unprocessable Entity/);
  });
});

// ============================================================
// getScreenplay
// ============================================================

describe("getScreenplay", () => {
  it("GET 单个任务的剧本", async () => {
    const screenplay = makeScreenplay();
    fetchMock.mockResolvedValueOnce(jsonResponse(screenplay));

    const result = await getScreenplay("t1");

    expect(result.meta.title).toBe("测试剧本");
    expect(fetchMock).toHaveBeenCalledWith("/api/screenplay/t1");
  });

  it("404 时抛出", async () => {
    fetchMock.mockResolvedValueOnce(jsonResponse({}, 404, "Not Found"));

    await expect(getScreenplay("nope")).rejects.toThrow(/Get screenplay failed: Not Found/);
  });
});

// ============================================================
// regenerateShot
// ============================================================

describe("regenerateShot", () => {
  it("路径带上 sceneId / shotId，并返回 shot", async () => {
    const screenplay = makeScreenplay();
    const newShot = makeShot({ shot_type: "大特写" });
    fetchMock.mockResolvedValueOnce(jsonResponse({ shot: newShot }));

    const shot = await regenerateShot("s01", "s01_01", screenplay, "压低机位");

    expect(shot.shot_type).toBe("大特写");
    expect(fetchMock.mock.calls[0][0]).toBe("/api/shots/s01/s01_01/regenerate");

    const body = JSON.parse(fetchMock.mock.calls[0][1].body as string);
    expect(body.user_feedback).toBe("压低机位");
    expect(body.current_screenplay.meta.title).toBe("测试剧本");
  });

  it("未传反馈时 user_feedback 为空字符串", async () => {
    fetchMock.mockResolvedValueOnce(jsonResponse({ shot: makeShot() }));

    await regenerateShot("s01", "s01_01", makeScreenplay());

    const body = JSON.parse(fetchMock.mock.calls[0][1].body as string);
    expect(body.user_feedback).toBe("");
  });

  it("500 时抛出", async () => {
    fetchMock.mockResolvedValueOnce(jsonResponse({}, 500, "Internal Server Error"));

    await expect(regenerateShot("s01", "s01_01", makeScreenplay())).rejects.toThrow(
      /Regenerate failed/,
    );
  });
});

// ============================================================
// 导出 URL（浏览器导航下载，不经过 fetch）
// ============================================================

describe("导出 URL", () => {
  it.each([
    ["yaml", getYamlUrl],
    ["zip", getZipUrl],
    ["manifest", getManifestUrl],
    ["word", getWordUrl],
  ])("%s 的 URL 拼接正确", (kind, build) => {
    expect(build("t1")).toBe(`/api/screenplay/t1/export/${kind}`);
  });
});

// ============================================================
// 历史记录：列表 / 删除 / 改名
// ============================================================

describe("fetchHistory", () => {
  it("GET /api/tasks", async () => {
    const items = [{ task_id: "t1", title: "标题", status: "done", created_at: "2026-01-01" }];
    fetchMock.mockResolvedValueOnce(jsonResponse(items));

    const result = await fetchHistory();

    expect(result).toHaveLength(1);
    expect(fetchMock).toHaveBeenCalledWith("/api/tasks");
  });

  it("非 2xx 时抛出", async () => {
    fetchMock.mockResolvedValueOnce(jsonResponse({}, 500, "Server Error"));

    await expect(fetchHistory()).rejects.toThrow("Failed to fetch history");
  });
});

describe("deleteTask", () => {
  it("DELETE /api/tasks/{id}", async () => {
    fetchMock.mockResolvedValueOnce(jsonResponse({ ok: true }));

    await deleteTask("t1");

    expect(fetchMock).toHaveBeenCalledWith("/api/tasks/t1", { method: "DELETE" });
  });

  it("404 时抛出", async () => {
    fetchMock.mockResolvedValueOnce(jsonResponse({}, 404, "Not Found"));

    await expect(deleteTask("nope")).rejects.toThrow("Failed to delete task");
  });
});

describe("renameTask", () => {
  it("PATCH /api/tasks/{id}/title", async () => {
    fetchMock.mockResolvedValueOnce(jsonResponse({ ok: true }));

    await renameTask("t1", "新标题");

    expect(fetchMock.mock.calls[0][0]).toBe("/api/tasks/t1/title");
    expect(fetchMock.mock.calls[0][1].method).toBe("PATCH");
    expect(JSON.parse(fetchMock.mock.calls[0][1].body as string)).toEqual({ title: "新标题" });
  });

  it("422 时抛出", async () => {
    fetchMock.mockResolvedValueOnce(jsonResponse({}, 422, "Unprocessable Entity"));

    await expect(renameTask("t1", "")).rejects.toThrow("Failed to rename task");
  });
});

describe("saveScreenplay", () => {
  it("PATCH /api/screenplay/{id}，body 包在 screenplay 字段里", async () => {
    const screenplay = makeScreenplay();
    fetchMock.mockResolvedValueOnce(jsonResponse({ ok: true }));

    await saveScreenplay("t1", screenplay);

    expect(fetchMock.mock.calls[0][0]).toBe("/api/screenplay/t1");
    expect(fetchMock.mock.calls[0][1].method).toBe("PATCH");
    const body = JSON.parse(fetchMock.mock.calls[0][1].body as string);
    expect(body.screenplay.meta.title).toBe("测试剧本");
  });

  it("非 2xx 时抛出", async () => {
    fetchMock.mockResolvedValueOnce(jsonResponse({}, 500, "Server Error"));

    await expect(saveScreenplay("t1", makeScreenplay())).rejects.toThrow(
      "Failed to save screenplay",
    );
  });
});

// ============================================================
// streamProgress（SSE）
// ============================================================

describe("streamProgress", () => {
  it("解析 data 行并分发到 onStage，done 时回调 onDone", async () => {
    fetchMock.mockResolvedValueOnce(
      sseResponse([
        'data: {"stage":"splitting","message":"切分","progress":0.05}\n\n',
        'data: {"stage":"done","message":"完成","progress":1}\n\n',
      ]),
    );

    const stages: PipelineStage[] = [];
    const done = new Promise<void>((resolve) => {
      streamProgress("t1", (s) => stages.push(s), resolve, () => {});
    });
    await done;

    expect(stages).toHaveLength(1);
    expect(stages[0].stage).toBe("splitting");
    expect(fetchMock.mock.calls[0][0]).toBe("/api/convert/t1/stream");
  });

  it("stage=error 时回调 onError 并带上后端消息", async () => {
    fetchMock.mockResolvedValueOnce(
      sseResponse(['data: {"stage":"error","message":"管线崩溃","progress":0}\n\n']),
    );

    const message = await new Promise<string>((resolve) => {
      streamProgress("t1", () => {}, () => {}, resolve);
    });

    expect(message).toBe("管线崩溃");
  });

  it("无法解析的行被跳过（不打断后续事件）", async () => {
    fetchMock.mockResolvedValueOnce(
      sseResponse([
        "data: 这不是 JSON\n\n",
        'data: {"stage":"extracting","message":"提取","progress":0.3}\n\n',
      ]),
    );

    const stages: PipelineStage[] = [];
    await new Promise<void>((resolve) => {
      streamProgress(
        "t1",
        (s) => stages.push(s),
        () => {},
        () => {},
      );
      // 没有 done 事件，等微任务跑完
      setTimeout(resolve, 50);
    });

    expect(stages).toHaveLength(1);
    expect(stages[0].stage).toBe("extracting");
  });

  it("fetch 拒绝时回调 onError", async () => {
    fetchMock.mockRejectedValueOnce(new Error("网络不通"));

    const message = await new Promise<string>((resolve) => {
      streamProgress("t1", () => {}, () => {}, resolve);
    });

    expect(message).toBe("网络不通");
  });

  it("AbortError 不触发 onError", async () => {
    const abortErr = new Error("aborted");
    abortErr.name = "AbortError";
    fetchMock.mockRejectedValueOnce(abortErr);

    const onError = vi.fn();
    streamProgress("t1", () => {}, () => {}, onError);
    await new Promise((r) => setTimeout(r, 50));

    expect(onError).not.toHaveBeenCalled();
  });

  it("返回 AbortController 用于取消", () => {
    fetchMock.mockResolvedValueOnce(sseResponse([]));

    const controller = streamProgress("t1", () => {}, () => {}, () => {});

    expect(controller).toBeInstanceOf(AbortController);
    expect(fetchMock.mock.calls[0][1].signal).toBe(controller.signal);
  });
});
