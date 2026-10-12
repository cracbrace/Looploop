"""
L4 API：测试数据库隔离的自我校验。

PR 04 的核心验收是「跑测试不污染真实 looploop.db」。人工比对 mtime 只能证明
「这一次没写坏」，证明不了「以后也不会」——有人删掉 `api_db` fixture 依赖、
或把 `DB_PATH` 改回模块级常量，mtime 那条人工检查不会在 CI 里报警。

所以把隔离本身写成可执行断言：
    1. `DB_PATH` 确实指向本次用例的 tmp 库，而不是项目根的 looploop.db
    2. POST /convert 建的任务只能从隔离库读出来

这两条一起，把「隔离」从一次性人工动作变成常驻护栏。
"""

from __future__ import annotations

from pathlib import Path

import backend.database as database

# backend/database.py 里原本硬编码的那个真实库位置
REAL_DB_PATH = (Path(database.__file__).parent.parent / "looploop.db").resolve()


def test_db_path_points_at_tmp_db_not_real_db(api_db):
    """隔离不变量：DB_PATH 必须被改写到 tmp_path 下的临时库。"""
    assert Path(database.DB_PATH).resolve() == api_db.resolve(), (
        f"DB_PATH 未被隔离：{database.DB_PATH}"
    )
    assert Path(database.DB_PATH).resolve() != REAL_DB_PATH, (
        f"DB_PATH 仍指向真实库，测试会污染它：{REAL_DB_PATH}"
    )


def test_convert_writes_task_into_isolated_db(client, sample_text, dispatched_pipelines):
    """
    POST /convert 建的任务必须能从隔离库读回来。

    走 HTTP 的 GET /api/tasks 而不是直接连库，是为了复用同一条 DB_PATH 通路，
    这样只要隔离断了，本用例和 `test_db_path_points_at_tmp_db_not_real_db` 会同时变红。
    """
    task_id = client.post("/api/convert", json={"text": sample_text}).json()["task_id"]

    tasks = client.get("/api/tasks").json()

    assert [t["task_id"] for t in tasks] == [task_id], f"got {tasks}"


def test_isolated_db_starts_empty(client):
    """每个用例都拿到一个全新的空库——用例之间不互相看见对方的数据。"""
    assert client.get("/api/tasks").json() == []
