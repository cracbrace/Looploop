"""
L4 API：`POST /api/shots/{scene_id}/{shot_id}/regenerate` —— 唯一的 Human-in-the-Loop 写接口。

覆盖对照（`Looploop_Test_PR_Plan.md` PR 11）：
    200 且 shot 字段 == FakeLLM 返回值
    局部更新语义：响应只含**一个**镜头，且不改写已存档的剧本
    上下文：prompt 里带目标镜头原始数据 + ±2 邻镜
    SafeParser 重试：先坏后好 → 200；一直坏 → 500
    404（shot 不存在，且**在调用 LLM 之前**就返回）
    422（缺 / 非法的 current_screenplay）

⚠️ 两处与计划书不同，都来自读码 + 实测：

1. **计划书说「回读 GET /screenplay：目标 shot_id 已变」——做不到，因为本端点根本不落库。**
   它只返回 `{"shot": {...}}`，完全是**无状态**的。持久化是前端的职责：
   `useScreenplay.handleRegenerateShot()` 在 React state 里做局部合并，
   然后（本该）调用 `PATCH /api/screenplay`。
   因此本文件把「防整剧覆写」这条意图**改成正确的靶子**：
   断言它**不写任何东西**，且响应只含单个镜头（前端若拿整份剧本去覆盖才是灾难）。

2. **路径里的 `scene_id` 完全不参与查找。** 路由只按 `shot_id` 全局搜索；
   这是良性的（`shot_id` 形如 `s01_01`，本身就编码了场景，全局唯一），
   但值得钉住 —— 哪天 shot_id 不再唯一，这里会变成静默改错镜头。
"""

from __future__ import annotations

import json

import allure
import pytest

from backend.models import Shot
from tests.fakes.fake_llm import (
    FakeLLM,
    make_regenerated_shot,
    make_valid_screenplay_dict,
    make_valid_shot,
)

pytestmark = [allure.feature("镜头重刷"), allure.severity(allure.severity_level.CRITICAL)]

TARGET_SHOT_ID = "s01_01"


@pytest.fixture
def five_shot_screenplay() -> dict:
    """
    单场景 5 个镜头，每个带可区分的 visual_prompt。

    用来验证上下文窗口 `all_shots[max(0, i-2) : i+3]`：目标是第 4 个镜头时，
    第 1 个镜头应当**落在窗口外**。
    """
    screenplay = make_valid_screenplay_dict()
    base = screenplay["scenes"][0]["shots"][0]

    screenplay["scenes"][0]["shots"] = [
        {
            **base,
            "shot_id": f"s01_{i:02d}",
            "shot_number": i,
            "visual_prompt": f"UNIQUE_PROMPT_{i} " + "x" * 25,
        }
        for i in range(1, 6)
    ]
    return screenplay


def _regenerate(client, screenplay: dict, shot_id: str = TARGET_SHOT_ID,
                scene_id: str = "s01", feedback: str | None = None):
    body: dict = {"current_screenplay": screenplay}
    if feedback is not None:
        body["user_feedback"] = feedback
    return client.post(f"/api/shots/{scene_id}/{shot_id}/regenerate", json=body)


# ============================================================
# 正常路径
# ============================================================

def test_regenerate_returns_the_new_shot(
    client, completed_task, completed_task_screenplay, fake_llm, monkeypatch
):
    """200，且响应里的 shot 就是 FakeLLM 给的那一只（逐字段，含默认值）。"""
    monkeypatch.setattr("backend.routes.get_llm", lambda: fake_llm)

    resp = _regenerate(client, completed_task_screenplay)

    assert resp.status_code == 200, resp.text
    assert set(resp.json()) == {"shot"}, f"响应形状变了：{sorted(resp.json())}"

    returned = Shot.model_validate(resp.json()["shot"])
    expected = Shot(**make_regenerated_shot())

    assert returned.model_dump() == expected.model_dump(), "返回的镜头与 mock 提供的不一致"
    assert fake_llm.prompts_containing("请重新生成"), "重刷请求没走到 LLM"


def test_regenerate_returns_exactly_one_shot_not_a_screenplay(
    client, completed_task_screenplay, fake_llm, monkeypatch
):
    """
    响应只含单个镜头——不是整份剧本。

    前端的合并逻辑是 `shots.map(s => s.shot_id === shotId ? newShot : s)`，
    它期望拿到一只镜头。若后端某天改成回整份剧本，前端会把这份剧本**整体替换**掉
    本地状态（局部编辑全丢），而且不会有任何报错。
    """
    monkeypatch.setattr("backend.routes.get_llm", lambda: fake_llm)

    body = _regenerate(client, completed_task_screenplay).json()

    assert list(body) == ["shot"], f"got {sorted(body)}"
    assert "scenes" not in body["shot"], "单个镜头里不该嵌套 scenes"
    assert "meta" not in body


def test_regenerate_does_not_touch_the_stored_screenplay(
    client, completed_task, completed_task_screenplay, fake_llm, monkeypatch
):
    """
    重刷**不落库**：已存档的剧本必须一字不改。

    这是本文件最重要的一条。计划书想防的是「整剧覆写」回归；
    对无状态端点来说，正确的靶子是「它根本不写」——
    一旦有人"顺手"在这里加了保存逻辑，就可能用一只镜头覆盖掉整份剧本。
    """
    monkeypatch.setattr("backend.routes.get_llm", lambda: fake_llm)

    before = client.get(f"/api/screenplay/{completed_task}").json()
    assert _regenerate(client, before).status_code == 200
    after = client.get(f"/api/screenplay/{completed_task}").json()

    assert after == before, "重刷接口改写了已存档的剧本——局部合并与持久化应属前端职责"


# ============================================================
# prompt 内容：上下文窗口与用户反馈
# ============================================================

def test_regenerate_prompt_carries_target_shot_and_context(
    client, completed_task_screenplay, fake_llm, monkeypatch
):
    """prompt 必须带上目标镜头的原始数据，以及「仅供参考、不要修改」的上下文区块。"""
    monkeypatch.setattr("backend.routes.get_llm", lambda: fake_llm)

    _regenerate(client, completed_task_screenplay)

    prompt = fake_llm.prompts_containing("请重新生成")[0]
    original = completed_task_screenplay["scenes"][0]["shots"][0]

    assert original["visual_prompt"] in prompt, "目标镜头的原始数据没进 prompt"
    assert "上下文镜头" in prompt, "缺少上下文区块"
    assert "用户反馈：请自由发挥" in prompt, "未提供反馈时应回落默认文案"


def test_regenerate_prompt_context_window_is_two_either_side(
    client, five_shot_screenplay, fake_llm, monkeypatch
):
    """
    上下文窗口是目标 ±2 个镜头：目标为第 4 个时，第 1 个必须落在窗口外。

    窗口过宽会把整场戏塞进 prompt（费钱 + 干扰），过窄则失去局部连贯性。
    """
    monkeypatch.setattr("backend.routes.get_llm", lambda: fake_llm)

    _regenerate(client, five_shot_screenplay, shot_id="s01_04")

    prompt = fake_llm.prompts_containing("请重新生成")[0]

    assert "UNIQUE_PROMPT_4" in prompt, "目标镜头本身必须在 prompt 里"
    for i in (2, 3, 5):
        assert f"UNIQUE_PROMPT_{i}" in prompt, f"第 {i} 个镜头应落在 ±2 窗口内"
    assert "UNIQUE_PROMPT_1" not in prompt, "第 1 个镜头超出 ±2 窗口，不该出现"


def test_regenerate_prompt_carries_user_feedback(
    client, completed_task_screenplay, fake_llm, monkeypatch
):
    """用户填写的反馈必须原样进 prompt——这是 Human-in-the-loop 的全部意义。"""
    monkeypatch.setattr("backend.routes.get_llm", lambda: fake_llm)

    _regenerate(client, completed_task_screenplay, feedback="把机位压低一点，加个雨")

    prompt = fake_llm.prompts_containing("请重新生成")[0]

    assert "用户反馈：把机位压低一点，加个雨" in prompt


# ============================================================
# SafeParser 重试路径
# ============================================================

def test_regenerate_retries_once_when_first_shot_is_invalid(
    client, completed_task, completed_task_screenplay, monkeypatch
):
    """
    「先坏后好」：首次返回非法镜头（visual_prompt 过短），
    SafeParser 把错误喂回 LLM 再要一次 → 第二次合法 → 200。

    `validate_single_shot` 的修正循环只有**一次**机会，所以脚本给两条即可。
    """
    scripted = FakeLLM(responses=[
        json.dumps(make_valid_shot(visual_prompt="too short")),
        json.dumps(make_regenerated_shot()),
    ])
    monkeypatch.setattr("backend.routes.get_llm", lambda: scripted)

    resp = _regenerate(client, completed_task_screenplay)

    assert resp.status_code == 200, resp.text
    assert scripted.call_count == 2, f"期望「首次失败 + 一次修正」，实际调了 {scripted.call_count} 次"
    assert "请修正" in scripted.calls[1].prompt, "第二次调用应当是修正请求"
    assert "too short" not in resp.json()["shot"]["visual_prompt"]


def test_regenerate_500_when_llm_keeps_returning_invalid_shot(
    client, completed_task, completed_task_screenplay, monkeypatch
):
    """两次都坏 → 修正机会用尽 → 路由兜成 500 并说明是重刷失败（不是 200 + 坏镜头）。"""
    bad = json.dumps(make_valid_shot(visual_prompt="too short"))
    scripted = FakeLLM(responses=[bad, bad])
    monkeypatch.setattr("backend.routes.get_llm", lambda: scripted)

    resp = _regenerate(client, completed_task_screenplay)

    assert resp.status_code == 500, f"got {resp.status_code}"
    assert "镜头重刷失败" in resp.json()["detail"], f"got {resp.json()['detail']!r}"
    assert scripted.call_count == 2


def test_regenerate_500_when_llm_returns_unparseable_json(
    client, completed_task, completed_task_screenplay, monkeypatch
):
    """LLM 返回的不是 JSON → SafeParseError（不是 ValidationError）也要被兜成 500。"""
    scripted = FakeLLM(responses=["这不是 JSON", "这也不是"])
    monkeypatch.setattr("backend.routes.get_llm", lambda: scripted)

    resp = _regenerate(client, completed_task_screenplay)

    assert resp.status_code == 500, f"got {resp.status_code}"
    assert "镜头重刷失败" in resp.json()["detail"]


# ============================================================
# 404 / 422
# ============================================================

def test_regenerate_404_when_shot_not_found(
    client, completed_task_screenplay, fake_llm, monkeypatch
):
    """不存在的 shot_id → 404，且**在调用 LLM 之前**返回（不该白花一次 API 调用）。"""
    monkeypatch.setattr("backend.routes.get_llm", lambda: fake_llm)

    resp = _regenerate(client, completed_task_screenplay, shot_id="s99_99")

    assert resp.status_code == 404, f"got {resp.status_code}"
    assert "s99_99" in resp.json()["detail"], f"got {resp.json()['detail']!r}"
    assert fake_llm.call_count == 0, "404 之前就调了 LLM —— 白白花钱"


def test_regenerate_404_for_empty_screenplay(client, fake_llm, monkeypatch):
    """剧本里一个镜头都没有 → 同样 404，而不是 IndexError。"""
    monkeypatch.setattr("backend.routes.get_llm", lambda: fake_llm)

    resp = _regenerate(client, {"scenes": []}, shot_id="s01_01")

    assert resp.status_code == 404, f"got {resp.status_code}"
    assert fake_llm.call_count == 0


def test_regenerate_looks_up_shot_by_id_only_ignoring_scene_id(
    client, completed_task_screenplay, fake_llm, monkeypatch
):
    """
    路径里的 scene_id **不参与查找**——只按 shot_id 全局搜索。

    良性：`shot_id` 形如 `s01_01`，本身已编码场景，全局唯一。
    钉住它是为了记录这处实现意外：哪天 shot_id 不再唯一，这里会静默改错镜头。
    """
    monkeypatch.setattr("backend.routes.get_llm", lambda: fake_llm)

    resp = _regenerate(client, completed_task_screenplay, scene_id="WRONG_SCENE")

    assert resp.status_code == 200, f"got {resp.status_code}"


@pytest.mark.parametrize(
    "payload, case",
    [
        ({}, "缺少 current_screenplay"),
        ({"current_screenplay": "not-a-dict"}, "传字符串"),
        ({"current_screenplay": []}, "传数组"),
    ],
    ids=["missing-key", "string", "list"],
)
def test_regenerate_rejects_non_object_screenplay(client, payload, case):
    """`RegenerateRequest.current_screenplay: dict` 要求是 JSON 对象。"""
    resp = client.post(f"/api/shots/s01/{TARGET_SHOT_ID}/regenerate", json=payload)

    assert resp.status_code == 422, f"{case}: got {resp.status_code}"
    assert isinstance(resp.json()["detail"], list), f"{case}: got {resp.json()['detail']!r}"
