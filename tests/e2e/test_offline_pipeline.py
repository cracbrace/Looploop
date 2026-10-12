"""
L3 端到端：零 API 成本、不依赖网络的全链路离线测试。

链路：POST /api/convert → 后台 Pipeline（FakeLLM 驱动）→ SSE 收到 done
      → GET /api/screenplay/{task_id} 拿到通过 Pydantic 校验的剧本。

这是 mock 章节的核心 PR，也是 PR 10（SSE）、PR 11（重刷）的复用基座。

注入点说明
---------
`backend/routes.py` 的懒加载单例是唯一需要替换的地方：

    get_llm()      → LLMClient()        ← 替换它
    get_pipeline() → Pipeline(get_llm()) ← 会自动拿到 FakeLLM，无需单独替换

`get_pipeline()` 内部调用的是模块级 `get_llm`，因此在测试里 patch
`backend.routes.get_llm` 后，`get_pipeline()` 会构造出「真 Pipeline + 假 LLM」——
被测的编排逻辑是真的，只有外部网络边界是假的。这就是 mock 该有的粒度。

反向验证
-------
`test_without_fake_the_pipeline_fails` 是这一节的负向对照：
不打 patch 时后台 Pipeline 必须失败。没有它，前一条用例的绿证明不了
「是 mock 让链路跑通的」——也可能链路压根没跑。
"""

from __future__ import annotations

import json
import time

import allure
import pytest

from backend.models import Screenplay
from tests.fakes.fake_llm import FAKE_CHARACTER, FAKE_DIALOGUE_LINE, FAKE_LOCATION

pytestmark = [allure.feature("离线全链路"), allure.severity(allure.severity_level.CRITICAL)]

#: 单条 SSE 流的消费上限（秒）
SSE_DEADLINE_SECONDS = 10.0


def _consume_sse(client, task_id: str) -> tuple[str, list[dict]]:
    """
    消费**完整的** SSE 响应体，返回 (content-type, 事件列表)。

    ⚠️ 这不是流式消费，而是「等整个响应体收完再解析」。

    实测（PR 10）：Starlette 的 `_TestClientTransport` 把响应体收进 `io.BytesIO()`
    再一次性交付，`iter_lines()` 在生成器结束之前**一行都拿不到**。
    因此下面的 deadline 检查只能对已缓冲的内容做事后判断，**挡不住挂死**：
    若 SSE 生成器永不终止，`iter_lines()` 会一直阻塞，检查一次都执行不到
    （实测过一次 300s 挂死，是被外层超时掐掉的，不是被这里）。

    真正兜底的是 pytest.ini 里的全局 `timeout`（pytest-timeout），
    它把「挂死」压成「失败」。需要验证「增量投递 / 心跳实时到达」的用例，
    请用 `tests/api/conftest.py` 的 `live_server` fixture 走真 HTTP。
    """
    events: list[dict] = []
    deadline = time.monotonic() + SSE_DEADLINE_SECONDS

    with client.stream("GET", f"/api/convert/{task_id}/stream") as response:
        assert response.status_code == 200, f"got {response.status_code}"
        content_type = response.headers.get("content-type", "")

        for line in response.iter_lines():
            # 事后 sanity bound：能走到这里说明响应体已经收完，
            # 它不会（也无法）拦截阻塞中的流。
            assert time.monotonic() < deadline, (
                f"SSE 响应体消费耗时超过 {SSE_DEADLINE_SECONDS}s，"
                f"已收到事件：{events}"
            )
            # 空行为 SSE 帧分隔符；": ..." 为注释心跳
            if not line or line.startswith(":"):
                continue
            assert line.startswith("data:"), f"非预期 SSE 行：{line!r}"
            events.append(json.loads(line[len("data:"):].strip()))

    return content_type, events


def test_offline_pipeline_runs_end_to_end(client, fake_llm, monkeypatch, sample_text):
    """断网也能跑通的全链路：convert → SSE done → 合法剧本。"""
    monkeypatch.setattr("backend.routes.get_llm", lambda: fake_llm)

    convert_resp = client.post(
        "/api/convert", json={"text": sample_text, "title": "离线测试"}
    )
    assert convert_resp.status_code == 200, convert_resp.text
    task_id = convert_resp.json()["task_id"]

    content_type, events = _consume_sse(client, task_id)

    assert content_type.startswith("text/event-stream"), f"got {content_type!r}"
    assert events, "SSE 未收到任何 data 事件"

    # ── mock 是否真的生效：不能只看「链路绿了」 ──
    assert fake_llm.call_count > 0, "FakeLLM 从未被调用——说明 mock 没接上，绿是假的"
    assert fake_llm.prompts_containing("characters_found"), (
        "FakeLLM 没有收到过逐段提取请求，链路走的不是预期分支"
    )

    # ── SSE 终态 ──
    assert events[-1]["stage"] == "done", f"终态不是 done：{events[-1]}"

    # ── 落库结果必须是合法剧本 ──
    screenplay_resp = client.get(f"/api/screenplay/{task_id}")
    assert screenplay_resp.status_code == 200, screenplay_resp.text

    screenplay = Screenplay.model_validate(screenplay_resp.json())

    assert screenplay.meta.title == "离线测试", f"got '{screenplay.meta.title}'"
    assert screenplay.scenes, "剧本没有场景"
    assert screenplay.characters, "角色表为空"

    shot_types = {shot.shot_type for scene in screenplay.scenes for shot in scene.shots}
    assert shot_types == {"远景", "近景"}, (
        f"景别 {shot_types} 与 FakeLLM 提供的 {FAKE_LOCATION} 数据不符——"
        "说明剧本并非来自 FakeLLM"
    )
    assert any(FAKE_LOCATION in scene.location for scene in screenplay.scenes)

    dialogue_lines = [
        shot.dialogue.line
        for scene in screenplay.scenes
        for shot in scene.shots
        if shot.dialogue
    ]
    assert FAKE_DIALOGUE_LINE in dialogue_lines, f"got {dialogue_lines}"


def test_offline_pipeline_creates_characters_from_fake_data(client, fake_llm, monkeypatch, sample_text):
    """角色消歧链路也要走通：FakeLLM 报的 characters_found 必须落成角色表。"""
    monkeypatch.setattr("backend.routes.get_llm", lambda: fake_llm)

    task_id = client.post("/api/convert", json={"text": sample_text}).json()["task_id"]
    _consume_sse(client, task_id)

    screenplay = Screenplay.model_validate(client.get(f"/api/screenplay/{task_id}").json())

    names = [c.canonical_name for c in screenplay.characters]
    assert names == [FAKE_CHARACTER], f"got {names}"

    # 对白引用的 character_id 必须真实存在于角色表（跨模块一致性）
    dialogue_ids = {
        shot.dialogue.character_id
        for scene in screenplay.scenes
        for shot in scene.shots
        if shot.dialogue
    }
    assert dialogue_ids <= {c.character_id for c in screenplay.characters}


def _wait_for_error_response(client, task_id: str, deadline_seconds: float = 10.0):
    """
    轮询直到任务进入 error 终态，返回那次 GET /api/screenplay 的响应。

    为什么这里不用 SSE：`_run_pipeline_v045` 的**错误路径**是
    「先 `queue.put(error)` 再 `update_task(status="error")`」——SSE 一收到 error
    事件就断开，而那次数据库写入可能还在飞行中；用例随后结束、portal 关掉事件循环，
    aiosqlite 的工作线程就会向已关闭的 loop 回调，抛
    `RuntimeError: Event loop is closed`（表现为 PytestUnhandledThreadExceptionWarning）。

    轮询「直到 GET /api/screenplay 返回 500」恰好等到那次写入落地：
    状态是同一个 update_task 写进去的，返回 500 就意味着它已经完成。
    这样不碰生产代码，也不用 sleep 猜时间。

    （成功路径没有这个问题：它是「先 update_task 落库、再 queue.put(done)」，
    所以 SSE 收到 done 时数据一定已经写完。）
    """
    deadline = time.monotonic() + deadline_seconds
    while time.monotonic() < deadline:
        response = client.get(f"/api/screenplay/{task_id}")
        if response.status_code != 200:
            return response
        time.sleep(0.05)

    raise AssertionError(f"等待任务 {task_id} 进入 error 终态超时（{deadline_seconds}s）")


def test_without_fake_the_pipeline_fails(client, sample_text):
    """
    反向验证（negative control）：不打 patch 时后台 Pipeline 必须失败。

    根 conftest 的 `isolate_external_deps` 会让 `backend.routes.LLMClient`
    实例化即抛错，因此这里是**快速失败**，不会真的联网。
    """
    task_id = client.post("/api/convert", json={"text": sample_text}).json()["task_id"]

    response = _wait_for_error_response(client, task_id)

    assert response.status_code == 500, f"预期失败，实际 {response.status_code}"
    assert "LLMClient" in response.json()["detail"], f"got {response.json()['detail']!r}"


def test_unknown_prompt_makes_fake_llm_complain():
    """
    替身自身的契约测试：prompt 无法识别时必须显式报错。

    这条防的是「新增了一条 LLM 调用路径，但 FakeLLM 默默返回了不相关数据，
    于是测试变成假绿」。让替身吵闹，比让它安静地骗人安全得多。
    """
    import asyncio

    from tests.fakes.fake_llm import FakeLLM

    with pytest.raises(AssertionError, match="无法识别"):
        asyncio.run(FakeLLM().generate_json("一段与任何已知分支都不匹配的提示词"))
