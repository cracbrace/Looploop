"""
L4 API 层的 fixture：测试数据库隔离 + 外部依赖隔离。

背景：`backend/database.py` 的 `DB_PATH` 是模块级常量，硬编码指向项目根的
`looploop.db`。不隔离的话，每次跑 API 测试都会往**真实任务历史表**写数据，
污染开发者的历史记录（这也是 PR 04 存在的首要理由）。

本文件建立两道隔离：

1. 文件隔离 —— `DB_PATH` 指向 pytest 的 `tmp_path`，用例结束即随临时目录销毁。
   `backend.database` 里的函数都在调用时才读模块级 `DB_PATH`，
   而 routes.py 导入的是函数对象本身，因此只 patch 常量即可全局生效。

2. 依赖隔离 —— `tests/api` 下任何用例都不得触达真实 LLM API。
   这里把 `backend.routes.get_llm` 换成立即抛错的替身：`_run_pipeline_v045`
   在 `get_pipeline()` 处就会失败并立刻把任务标记为 error，
   既不发网络请求、也不触发 Pipeline 的重试 sleep。
   PR 06 的 FakeLLM 会在此基础上提供「能跑通全链路」的替身。
"""

from __future__ import annotations

import asyncio

import pytest
from fastapi.testclient import TestClient

from backend.database import init_db


@pytest.fixture
def api_db(tmp_path, monkeypatch):
    """把 DB_PATH 指向本次用例专属的临时库，并建好表结构。"""
    db_path = tmp_path / "looploop_test.db"
    monkeypatch.setattr("backend.database.DB_PATH", db_path)

    asyncio.run(init_db())

    return db_path


@pytest.fixture(autouse=True)
def isolate_external_deps(monkeypatch):
    """
    清空路由层的懒加载单例与事件总线，并封死真实 LLM。

    单例（_llm / _pipeline / _parser）和 NOTIFICATION_BUS 都是模块级可变全局，
    不重置会让上一个用例的状态漏进下一个用例——这类串味 bug 比测试失败更难查。
    """
    monkeypatch.setattr("backend.routes._llm", None)
    monkeypatch.setattr("backend.routes._pipeline", None)
    monkeypatch.setattr("backend.routes._parser", None)
    monkeypatch.setattr("backend.routes.NOTIFICATION_BUS", {})

    def _no_real_llm():
        raise RuntimeError(
            "tests/api 禁止构造真实 LLMClient；需要可用的 LLM 替身请用 PR 06 的 FakeLLM"
        )

    monkeypatch.setattr("backend.routes.get_llm", _no_real_llm)


@pytest.fixture
def client(api_db):
    """
    基于隔离 DB 的 TestClient。

    用 `with` 进入上下文管理器是为了走真实的 lifespan 启动路径
    （uvicorn 启动时同样会执行它）；其内部的 init_db() 与 api_db 指向同一个
    临时文件，重复执行是幂等的。
    """
    from backend.main import app

    with TestClient(app) as test_client:
        yield test_client


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
