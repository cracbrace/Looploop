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
def live_server(api_db, isolate_external_deps):
    """
    在后台线程里真起一个 uvicorn，返回它的 base URL（端口由系统分配）。

    为什么必须有它：已实测 Starlette 的 `_TestClientTransport` 会把整个响应体收进
    `io.BytesIO()` 再一次性交付。所以 TestClient **无法**证明「SSE 是边产生边到达的」，
    也**无法**证明心跳在静默期真的送到了客户端 —— 而这正是前端
    `fetch` + `ReadableStream` 增量解析进度条所依赖的性质。

    与 monkeypatch 的配合：uvicorn 跑在同一进程的后台线程里，因此
    `api_db`（DB_PATH 改写）与 `isolate_external_deps`（路由层单例重置 +
    真实 LLM 守卫）的 patch 对服务器同样生效，不需要额外同步。
    依赖顺序也保证了：服务器先停，monkeypatch 再还原。
    """
    import threading
    import time as _time

    import uvicorn

    from backend.main import app

    config = uvicorn.Config(
        app, host="127.0.0.1", port=0, log_level="warning", access_log=False
    )
    server = uvicorn.Server(config)
    thread = threading.Thread(target=server.run, name="looploop-live-server", daemon=True)
    thread.start()

    startup_deadline = _time.monotonic() + 15.0
    while not server.started:
        if _time.monotonic() > startup_deadline:
            server.should_exit = True
            raise RuntimeError("uvicorn 未能在 15s 内启动")
        _time.sleep(0.02)

    port = server.servers[0].sockets[0].getsockname()[1]

    yield f"http://127.0.0.1:{port}"

    server.should_exit = True
    thread.join(timeout=10)
    assert not thread.is_alive(), "uvicorn 线程未按时退出"


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
    error: str | None = None,
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
        if status != "pending" or screenplay is not None or error is not None:
            kwargs: dict = {"status": status}
            if screenplay is not None:
                kwargs.update(result=screenplay, progress=1.0, stage="done")
            if error is not None:
                kwargs["error"] = error
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


#: `completed_task` 的固定 id 与剧本标题（导出类断言需要「与源数据逐字段一致」的参照）
COMPLETED_TASK_ID = "bbbb00000001"
COMPLETED_SCREENPLAY_TITLE = "原始标题"


@pytest.fixture
def completed_task_screenplay() -> dict:
    """`completed_task` 里那份剧本的原始内容——供「导出后应与之一致」的断言使用。"""
    return make_valid_screenplay_dict(title=COMPLETED_SCREENPLAY_TITLE)


@pytest.fixture
def completed_task(api_db, completed_task_screenplay) -> str:
    """
    一个 status=done 且带合法剧本的任务。

    PR 09（剧本查询 / 导出）与 PR 11（单镜头重刷）都复用本 fixture——
    只有 done + result 齐备的任务才会被 `GET /api/screenplay/{id}` 原样返回。
    """
    _seed_task(COMPLETED_TASK_ID, "已完成任务", status="done",
               screenplay=completed_task_screenplay)
    return COMPLETED_TASK_ID


@pytest.fixture
def failed_task(api_db) -> str:
    """一个 status=error 的任务，用于 `GET /api/screenplay` 的 500 分支。"""
    task_id = "eeee00000001"
    _seed_task(task_id, "失败任务", status="error", error="模拟管线崩溃")
    return task_id


#: 标题为纯 ASCII 的已完成任务（见下方 fixture 的说明）
ASCII_TASK_ID = "abcd00000001"


@pytest.fixture
def ascii_titled_screenplay() -> dict:
    return make_valid_screenplay_dict(title="Ascii Screenplay")


@pytest.fixture
def ascii_titled_task(api_db, ascii_titled_screenplay) -> str:
    """
    一个标题为纯 ASCII 的 done 任务。

    存在的理由：`export/zip` 把剧本标题拼进 `Content-Disposition` 的 filename，
    而 Starlette 用 **latin-1** 编码 header 值——中文标题会让该端点直接抛
    `UnicodeEncodeError`（500，见 test_screenplay_export 里对应的 xfail）。

    为了让 ZIP 的**格式**断言（is_zipfile / 成员齐全 / 内嵌素材清单）继续跑，
    就需要一份能通过 header 编码的输入。等缺陷修好，这个 fixture 就可以退休。
    """
    _seed_task(ASCII_TASK_ID, "ASCII task", status="done",
               screenplay=ascii_titled_screenplay)
    return ASCII_TASK_ID


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
