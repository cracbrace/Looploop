"""
L4 API：剧本导出端点的存在性与 404 语义。

迁移自 backend/test_pipeline.py::test_api_export_endpoints_exist。

本文件在 PR 04 只固化两条基线：
    1. 不存在的 task_id → 404（而不是 500 或 200 空体）
    2. 路由本身确实注册在 OpenAPI schema 里
第 2 条是本 PR 相对旧脚本的改进：旧脚本用「返回 404」推断「路由存在」，
但 404 无法区分「路由没注册」和「任务不存在」——路由写错前缀时旧检查照样绿。

PR 09 会在本文件补齐 4 个导出端点的响应体格式断言（YAML 可 load / Word 可打开 /
ZIP 魔数），届时 404 矩阵也会扩到 manifest 与 zip。
"""

from __future__ import annotations

import pytest

# PR 04 只覆盖旧脚本检查过的两个端点；manifest / zip 由 PR 09 补齐
LEGACY_EXPORT_KINDS = ["yaml", "word"]


@pytest.mark.parametrize("kind", LEGACY_EXPORT_KINDS)
def test_export_returns_404_for_unknown_task(client, kind):
    """不存在的 task_id 必须 404，并带可读的 detail。"""
    resp = client.get(f"/api/screenplay/nonexistent/export/{kind}")

    assert resp.status_code == 404, f"{kind}: got {resp.status_code}"
    assert resp.json().get("detail"), f"{kind}: 404 应带 detail 说明"


@pytest.mark.parametrize("kind", LEGACY_EXPORT_KINDS)
def test_export_route_is_registered(client, kind):
    """路由存在性的精确检查——盯 OpenAPI schema，而不是从 404 反推。"""
    paths = client.get("/openapi.json").json()["paths"]

    assert f"/api/screenplay/{{task_id}}/export/{kind}" in paths, (
        f"{kind}: 路由未注册，已注册路径：{sorted(paths)}"
    )
