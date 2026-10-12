"""
L4 API：`GET /api/convert/{task_id}/stream` —— 全项目最难测也最关键的端点。

它是前端进度条的唯一数据源，历史上出过 SSE 竞态（`pr/29`）与心跳缺失（`pr/78`）。
PR 10 用 FakeLLM 驱动**可预测**的事件序列，把 SSE 协议细节钉下来。

两种消费方式，各管一段（这是本文件最重要的设计决定）：

┌────────────────┬──────────────────────────────────────────────────────────────┐
│ TestClient     │ 响应体被 Starlette 整包缓冲（实测），适合断言**内容**：       │
│                │ content-type / 事件集合 / 顺序 / 终态 / progress 单调 / 心跳发出 │
├────────────────┼──────────────────────────────────────────────────────────────┤
│ live_server    │ 真 uvicorn + 真 HTTP，适合断言**投递方式**：                  │
│                │ 事件是边产生边到达的、心跳在静默期真的送到客户端              │
└────────────────┴──────────────────────────────────────────────────────────────┘

计划书原文写「`TestClient.stream` 支持逐行消费」——实测**不成立**
（`_TestClientTransport` 收完整个 body 才交付），因此「长时间监听下心跳行存在」
这类断言必须换 `live_server` 走真 HTTP。内容类断言不受影响，继续用 TestClient 更快。
"""

from __future__ import annotations

import json
import time

import allure
import httpx
import pytest

pytestmark = [allure.feature("SSE 进度流"), allure.severity(allure.severity_level.CRITICAL)]

#: 心跳间隔注入值：把 15s 压到 0.1s，心跳测试才能在 1 秒内跑完
FAST_HEARTBEAT = 0.1
#: FakeLLM 的人为延迟：制造足够长的「Pipeline 静默期」
FAKE_LLM_DELAY = 0.8


def _parse_sse(lines) -> tuple[list[dict], int]:
    """
    把 SSE 行序列拆成 (data 事件列表, 心跳条数)。

    SSE 帧格式：`data: {json}\\n\\n` 为事件；`': ping\\n\\n'` 为注释心跳；
    空行是帧分隔符。顺手把「非预期行」也变成断言，防止路由偷偷改了前缀却没被发现。
    """
    events: list[dict] = []
    pings = 0
    for line in lines:
        if not line:
            continue
        if line.startswith(":"):
            pings += 1
            continue
        assert line.startswith("data:"), f"非预期 SSE 行：{line!r}"
        events.append(json.loads(line[len("data:"):].strip()))
    return events, pings


def _stream(client, task_id: str):
    """打开 SSE 流（TestClient 版本）。"""
    return client.stream("GET", f"/api/convert/{task_id}/stream")


def _wait_for_persisted_error(client, task_id: str, deadline_seconds: float = 10.0) -> None:
    """
    等后台任务把 error 状态写进库。

    错误路径的顺序是「先 queue.put(error) 再 update_task(status='error')」，
    所以 SSE 一断开，那次写入可能还在飞行中；用例随即结束、portal 关掉事件循环，
    aiosqlite 的工作线程就会向已关闭的 loop 回调。
    轮询到 500 恰好等到写入落地（该状态就是同一次 update_task 写的）。
    """
    deadline = time.monotonic() + deadline_seconds
    while time.monotonic() < deadline:
        if client.get(f"/api/screenplay/{task_id}").status_code == 500:
            return
        time.sleep(0.05)
    raise AssertionError(f"等待任务 {task_id} 的 error 状态落库超时")


@pytest.fixture
def offline_task(client, fake_llm, monkeypatch, sample_text) -> str:
    """用 FakeLLM 起一个任务并返回 task_id（Pipeline 由替身驱动，全程离线）。"""
    monkeypatch.setattr("backend.routes.get_llm", lambda: fake_llm)
    return client.post("/api/convert", json={"text": sample_text, "title": "SSE 测试"}).json()["task_id"]


# ============================================================
# 404 与响应头
# ============================================================

def test_stream_returns_404_for_unknown_task(client):
    """不存在的 task_id：路由在构造 StreamingResponse **之前**就抛 404。"""
    resp = client.get("/api/convert/never-existed/stream")

    assert resp.status_code == 404, f"got {resp.status_code}"
    assert resp.json()["detail"] == "任务不存在"


def test_stream_sets_event_stream_headers(client):
    """响应头必须让中间层不要缓冲——否则前端进度条会一次性蹦到 100%。"""
    task_id = client.post("/api/convert", json={"text": "测" * 100}).json()["task_id"]

    with _stream(client, task_id) as resp:
        assert resp.status_code == 200, f"got {resp.status_code}"
        assert resp.headers["content-type"].startswith("text/event-stream"), (
            resp.headers["content-type"]
        )
        assert resp.headers["cache-control"] == "no-cache"
        assert resp.headers["x-accel-buffering"] == "no"


# ============================================================
# 事件内容（TestClient：整包缓冲后解析）
# ============================================================

def test_stream_events_carry_stage_and_progress(client, offline_task):
    """每条 data 事件都必须是 `{stage, message, progress, ...}` 形状。"""
    with _stream(client, offline_task) as resp:
        events, _ = _parse_sse(resp.iter_lines())

    assert events, "一条事件都没收到"

    for event in events:
        assert "stage" in event, f"缺少 stage：{event}"
        assert "progress" in event, f"缺少 progress：{event}"
        assert isinstance(event["progress"], (int, float)), f"progress 不是数字：{event}"
        assert 0.0 <= event["progress"] <= 1.0, f"progress 越界：{event}"


def test_stream_progress_is_monotonic_non_decreasing(client, offline_task):
    """
    progress 只能前进不能倒退。

    前端把它直接映射成进度条宽度；一旦倒退，用户会看到进度条来回弹。
    """
    with _stream(client, offline_task) as resp:
        events, _ = _parse_sse(resp.iter_lines())

    progresses = [event["progress"] for event in events]

    assert progresses == sorted(progresses), f"progress 出现倒退：{progresses}"


def test_stream_terminates_with_done_at_progress_one(client, offline_task):
    """终态必须是 done 且 progress == 1.0，否则前端会永远转圈。"""
    with _stream(client, offline_task) as resp:
        events, _ = _parse_sse(resp.iter_lines())

    assert events[-1]["stage"] == "done", f"终态不是 done：{events[-1]}"
    assert events[-1]["progress"] == 1.0, f"got {events[-1]['progress']}"


def test_stream_done_event_carries_summary(client, offline_task):
    """
    done 事件额外带一份摘要（场景/镜头/角色/时长）。

    这是前端「转换完成！」提示卡的数据源，不能悄悄丢字段。
    """
    with _stream(client, offline_task) as resp:
        events, _ = _parse_sse(resp.iter_lines())

    summary = events[-1].get("data")
    assert isinstance(summary, dict), f"done 事件没有 data 摘要：{events[-1]}"
    assert {"scenes", "shots", "characters", "duration"} <= set(summary), (
        f"摘要字段缺失：{sorted(summary)}"
    )


def test_stream_emits_error_terminal_when_pipeline_fails(client, sample_text):
    """
    Pipeline 挂掉时必须推一条 `stage=error` 并结束流。

    这里刻意**不**注入 FakeLLM：根 conftest 的守卫会让 `LLMClient` 实例化即抛错，
    于是后台任务快速失败。前端据此把进度条切成错误态，而不是一直转。
    """
    task_id = client.post("/api/convert", json={"text": sample_text}).json()["task_id"]

    with _stream(client, task_id) as resp:
        events, _ = _parse_sse(resp.iter_lines())

    # 先等错误状态落库，避免后台写入撞上 portal 关闭
    _wait_for_persisted_error(client, task_id)

    assert events[-1]["stage"] == "error", f"终态不是 error：{events[-1]}"
    assert "LLMClient" in events[-1]["message"], f"got {events[-1]['message']!r}"


# ============================================================
# 心跳
# ============================================================

def test_stream_emits_heartbeat_during_pipeline_silence(
    client, offline_task, fake_llm, monkeypatch
):
    """
    Pipeline 静默期必须发 `: ping` 注释心跳（`pr/78`）。

    做法：心跳间隔注入 0.1s、FakeLLM 延迟 0.8s，于是在 1 秒内就能造出足够长的静默期。
    否则要真等 15s 才能观察到一次心跳。

    ⚠️ 范围说明：这里数到的 ping 是在**响应体收完之后**从缓冲内容里读出来的，
    它证明「心跳被发出」，但**不**证明「心跳实时到达客户端」——
    后者见下面的 `live_server` 用例。
    """
    fake_llm.delay_seconds = FAKE_LLM_DELAY
    monkeypatch.setattr("backend.routes.HEARTBEAT_INTERVAL_SECONDS", FAST_HEARTBEAT)

    with _stream(client, offline_task) as resp:
        events, pings = _parse_sse(resp.iter_lines())

    assert pings >= 1, "整个静默期一条心跳都没发出"
    assert events[-1]["stage"] == "done", f"心跳挤掉了终态：{events[-1]}"


# ============================================================
# 真 HTTP：投递方式
# ============================================================

def test_sse_is_streamed_incrementally_over_real_http(
    live_server, fake_llm, monkeypatch, sample_text
):
    """
    真 uvicorn + 真 HTTP 下的**增量投递**与**心跳实时到达**。

    这是前端 `fetch` + `ReadableStream` 增量解析 SSE 所依赖的性质，
    也是 TestClient 结构上证明不了的部分（它整包缓冲）。

    判据：首个 data 事件必须**远早于**流结束时刻到达。
    若被缓冲，所有行会在流结束的同一瞬间一起出现，比值趋近 1。
    """
    fake_llm.delay_seconds = FAKE_LLM_DELAY
    monkeypatch.setattr("backend.routes.get_llm", lambda: fake_llm)
    monkeypatch.setattr("backend.routes.HEARTBEAT_INTERVAL_SECONDS", FAST_HEARTBEAT)

    timeout = httpx.Timeout(30.0, read=30.0)

    with httpx.Client(base_url=live_server, timeout=timeout) as http:
        convert = http.post("/api/convert", json={"text": sample_text, "title": "SSE 真 HTTP"})
        assert convert.status_code == 200, convert.text
        task_id = convert.json()["task_id"]

        events: list[dict] = []
        pings = 0
        first_event_at: float | None = None
        started = time.monotonic()

        with http.stream("GET", f"/api/convert/{task_id}/stream") as resp:
            assert resp.status_code == 200, f"got {resp.status_code}"
            assert resp.headers["content-type"].startswith("text/event-stream")

            for line in resp.iter_lines():
                if line.startswith(":"):
                    pings += 1
                    continue
                if not line:
                    continue
                assert line.startswith("data:"), f"非预期 SSE 行：{line!r}"
                events.append(json.loads(line[len("data:"):].strip()))
                if first_event_at is None:
                    first_event_at = time.monotonic() - started

        elapsed = time.monotonic() - started

    assert events, "一条事件都没收到"
    assert events[-1]["stage"] == "done", f"终态不是 done：{events[-1]}"
    assert pings >= 1, (
        "真 HTTP 下静默期没有收到心跳——连接会在真实网络里被中间层掐断"
    )

    assert first_event_at is not None, "从未收到 data 事件"
    assert first_event_at < elapsed / 2, (
        f"首个事件在 {first_event_at:.3f}s 才到、流在 {elapsed:.3f}s 结束——"
        "比值接近 1 说明整个响应体被缓冲后一次性交付，不是增量投递"
    )
