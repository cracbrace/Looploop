"""
L4 API：健康检查端点。

迁移自 backend/test_pipeline.py::test_api_health。

与 tests/test_smoke.py::test_health_endpoint 的分工（有意保留的重叠）：
    smoke  —— 「框架能起来且这条路由可达」，是迁移期的金丝雀，只有 2 个断言
    本文件 —— 「响应契约完整」，字段集合与取值属于 API 层的正式覆盖

两者盯的不是同一件事，因此不做合并。
"""

from __future__ import annotations

import allure
import pytest

pytestmark = [allure.feature("健康检查"), allure.severity(allure.severity_level.MINOR)]


def test_health_reports_ok_and_metadata(client):
    """/api/health 返回 200，且 status/app 字段稳定（原 check("status 200"/"status ok"/"app name")）。"""
    resp = client.get("/api/health")

    assert resp.status_code == 200, f"got {resp.status_code}"

    body = resp.json()
    assert body["status"] == "ok", f"got {body}"
    assert body["app"] == "Looploop", f"got {body}"
    assert body["version"], "version 不应为空"
    assert body["llm_model"], "llm_model 不应为空"
