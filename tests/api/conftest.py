"""
L4 API 层专属 fixture。

数据库隔离（`api_db`）、TestClient（`client`）、外部依赖隔离
（`isolate_external_deps`）与 `fake_llm` 都在**根 conftest** —— 因为
tests/e2e/ 的离线 E2E 同样需要它们，定义两份必然漂移。

这里只放「只有 API 层用得上」的辅助工具。
"""

from __future__ import annotations

import pytest


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
