"""
L4 API：POST /api/convert 的入参校验与受理语义。

迁移对照（backend/test_pipeline.py → 本文件）：
    test_api_convert_empty         → test_convert_rejects_too_short_text[empty|way-too-short|off-by-one]
    test_api_convert_too_short     → 同上（两类非法输入合并为 parametrize）
    test_api_convert_accepts_valid → test_convert_accepts_sample_text
                                     test_convert_accepts_text_exactly_at_min_length（新增边界）

约束来源：`ConvertRequest.text` 是 `Field(..., min_length=100)`，
因此边界值围绕 100 展开——99 必须拒、100 必须收。

本文件只覆盖「路由契约」（校验 + 建任务 + 派发）；Pipeline 本身的行为属于
L3/L2 层，由 PR 05、PR 06 用 FakeLLM 覆盖。
"""

from __future__ import annotations

import re

import allure
import pytest

pytestmark = [allure.feature("转换接口"), allure.severity(allure.severity_level.CRITICAL)]

# uuid4().hex[:12] —— 12 位小写十六进制
TASK_ID_PATTERN = re.compile(r"^[0-9a-f]{12}$")

MIN_TEXT_LENGTH = 100


@pytest.mark.parametrize(
    "text, case",
    [
        ("", "空字符串"),
        ("太短", "远短于下限"),
        ("短" * (MIN_TEXT_LENGTH - 1), "下限 - 1（差一个字符）"),
    ],
    ids=["empty", "way-too-short", "off-by-one"],
)
def test_convert_rejects_too_short_text(client, text, case):
    """
    非法入参必须 422，且错误必须定位到 body.text。

    断言 `detail` 的 loc 而不只是状态码：状态码只能说明「被拒了」，
    loc 才能说明「因为 text 太短而被拒」——否则别处任何 422 都能让测试变绿。
    """
    resp = client.post("/api/convert", json={"text": text})

    assert resp.status_code == 422, f"{case}: got {resp.status_code}"

    detail = resp.json()["detail"]
    assert isinstance(detail, list) and detail, f"{case}: detail 缺失或为空 — {detail}"
    assert detail[0]["loc"] == ["body", "text"], f"{case}: got loc={detail[0]['loc']}"


def test_convert_accepts_sample_text(client, sample_text, dispatched_pipelines):
    """合法文本 → 200 + 12 位 hex task_id + 已派发 Pipeline（原 check("accepts valid"/"returns task_id")）。"""
    resp = client.post("/api/convert", json={"text": sample_text, "title": "测试"})

    assert resp.status_code == 200, f"got {resp.status_code}"

    task_id = resp.json()["task_id"]
    assert task_id, "task_id 不应为空"
    assert TASK_ID_PATTERN.match(task_id), f"task_id 不是 12 位 hex: {task_id!r}"

    assert dispatched_pipelines == [{"task_id": task_id, "title": "测试"}], (
        f"Pipeline 未按预期派发: {dispatched_pipelines}"
    )


def test_convert_accepts_text_exactly_at_min_length(client, dispatched_pipelines):
    """边界包含性：min_length=100 意味着恰好 100 字符必须被接受，而不是被当作越界。"""
    resp = client.post("/api/convert", json={"text": "测" * MIN_TEXT_LENGTH})

    assert resp.status_code == 200, f"got {resp.status_code}"
    assert TASK_ID_PATTERN.match(resp.json()["task_id"])
    assert len(dispatched_pipelines) == 1, f"got {dispatched_pipelines}"
