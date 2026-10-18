"""
L4 API 层专属 fixture。

数据库隔离（`api_db`）、TestClient（`client`）、外部依赖隔离
（`isolate_external_deps`）与 `fake_llm` 都在**根 conftest** —— 因为
tests/e2e/ 的离线 E2E 同样需要它们，定义两份必然漂移。

这里只放「只有 API 层用得上」的辅助工具。
"""

from __future__ import annotations

import asyncio

import pytest

from backend.database import create_task, get_db, update_task
from tests.fakes.fake_llm import make_valid_screenplay_dict


@pytest.fixture
def dispatched_pipelines(monkeypatch):
    """
    拦截后台 Pipeline 的派发：只记录调用，不真的执行。

    为什么必须拦：TestClient 退出时会关掉 portal 的事件循环，而
    `asyncio.create_task(_run_pipeline_v045(...))` 派发的任务若还在写 SQLite，
    aiosqlite 的工作线程就会向已关闭的 loop 回调，抛
    `RuntimeError: Event loop is closed`（表现为 PytestUnhandledThreadExceptionWarning
    在后续用例上突然爆出来）。生产环境里 loop 与进程同生命周期，不存在这个竞态，
    所以这是纯粹的测试收尾问题，应当在测试层收敛。

    顺带把「路由确实派发了 Pipeline」变成可断言的事实——
    旧脚本只检查 200，路由即使忘了 `create_task` 也照样绿。

    注意这里刻意用**同步函数**记录、再返回一个空协程：
    `asyncio.create_task(_run_pipeline_v045(...))` 是先同步求值实参、再排期，
    所以记录发生在 `create_task` 之前；若把记录写进协程体里，
    要等事件循环调度才会执行，断言时会看到空列表。

    刻意不做成 autouse：PR 10 / PR 11 需要真实 Pipeline 配合 FakeLLM 跑完整链路。
    """
    dispatched = []

    def _record_pipeline_run(task_id, request):
        dispatched.append({"task_id": task_id, "title": request.title})

        async def _noop():
            return None

        return _noop()

    monkeypatch.setattr("backend.routes._run_pipeline_v045", _record_pipeline_run)

    return dispatched


# ============================================================
# 预置任务（任务管理簇 / 剧本编辑簇共用）
# ============================================================

#: `GET /api/tasks` 的响应契约（`database.list_tasks()` 的 SELECT 列）
TASK_LIST_FIELDS = frozenset({
    "task_id", "title", "status", "progress", "stage", "message",
    "created_at", "original_text",
})


def _seed_task(
    task_id: str,
    title: str = "Untitled",
    *,
    status: str = "pending",
    screenplay: dict | None = None,
    created_at: str | None = None,
) -> None:
    """
    直接往隔离库里预置一条任务，**绕开 POST /convert**（因此不触发 Pipeline）。

    为什么用 `asyncio.run()` 而不是复用 TestClient 的事件循环：
    预置发生在 fixture 阶段，此时 portal 里的循环由 TestClient 掌管，
    在外部往里塞协程只会引入新的竞态。数据库文件是共享的，各写各的连接即可
    （WAL 模式下并发读不成问题）。与 `api_db` 里的 `asyncio.run(init_db())` 同一套做法。

    created_at 必须能显式指定：SQLite 的 `CURRENT_TIMESTAMP` **只有秒级精度**，
    同一秒内插入的多行之间排序是未定义的——想断言 `ORDER BY created_at DESC`，
    就必须自己掌握排序键。
    """

    async def _run() -> None:
        await create_task(task_id, title)
        if status != "pending" or screenplay is not None:
            kwargs: dict = {"status": status}
            if screenplay is not None:
                kwargs.update(result=screenplay, progress=1.0, stage="done")
            await update_task(task_id, **kwargs)
        if created_at is not None:
            conn = await get_db()
            await conn.execute(
                "UPDATE tasks SET created_at = ? WHERE task_id = ?", (created_at, task_id)
            )
            await conn.commit()
            await conn.close()

    asyncio.run(_run())


@pytest.fixture
def task_factory():
    """
    把 `_seed_task()` 作为 fixture 暴露，便于用例内追加预置数据。

    用 fixture 而不是让用例 `import conftest`：pytest 在无 `__init__.py` 的目录下
    会把 conftest 当**顶层模块**导入，而 `import tests.api.conftest` 会拿到另一个
    模块实例。对纯常量/函数而言两者等价、看不出问题，但那是颗定时炸弹
    （一旦 conftest 里出现模块级可变状态就会分裂）。fixture 是唯一权威入口。
    """
    return _seed_task


@pytest.fixture
def seeded_task(api_db) -> str:
    """一个 pending 任务，用于改名 / 删除。"""
    task_id = "aaaa00000001"
    _seed_task(task_id, "原初标题")
    return task_id


@pytest.fixture
def completed_task(api_db) -> str:
    """
    一个 status=done 且带合法剧本的任务。

    PR 09（剧本查询 / 导出）与 PR 11（单镜头重刷）都复用本 fixture——
    只有 done + result 齐备的任务才会被 `GET /api/screenplay/{id}` 原样返回。
    """
    task_id = "bbbb00000001"
    _seed_task(task_id, "已完成任务", status="done",
              screenplay=make_valid_screenplay_dict(title="原始标题"))
    return task_id


@pytest.fixture
def tasks_with_explicit_times(api_db) -> list[tuple[str, str, str]]:
    """3 个 created_at 显式错开的任务，供列表排序断言使用。"""
    plan = [
        ("cccc00000001", "最早的", "2024-01-01 00:00:00"),
        ("cccc00000002", "中间的", "2024-01-02 00:00:00"),
        ("cccc00000003", "最新的", "2024-01-03 00:00:00"),
    ]
    for task_id, title, created_at in plan:
        _seed_task(task_id, title, created_at=created_at)
    return plan
