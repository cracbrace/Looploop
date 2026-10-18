"""
Looploop pytest 全局 fixture 与共享测试数据。

分层约定（对应旧 backend/test_pipeline.py 的 L1-L4）：
    tests/unit/          L1 单元      —— 单个函数 / 数据模型的边界
    tests/integration/   L2 模块集成  —— 模块间的数据流与契约
    tests/api/           L4 接口      —— HTTP 端点行为（状态码矩阵 + 响应体格式）
    tests/e2e/           L3 端到端    —— Pipeline 全链路

fixture 归属：
    sample_text              所有层共享的输入文本
    api_db / client          测试数据库隔离 + 真实 lifespan（PR 04 建立在 tests/api，PR 06 提升到根）
    isolate_external_deps    禁止真实 LLM + 清空路由层单例（同上）
    fake_llm                 LLMClient 的离线替身（PR 06）

为什么隔离 fixture 在 PR 06 从 tests/api/conftest.py 提升到根 conftest：
PR 06 的离线 E2E 位于 tests/e2e/，PR 10 的 SSE 测试位于 tests/api/，
两处都需要「隔离库 + 禁止真实 LLM」的同一个 client；
放两份必然随时间漂移，因此只保留一份定义。
"""

from __future__ import annotations

import asyncio

import pytest
from fastapi.testclient import TestClient

from backend.database import init_db
from tests.fakes.fake_llm import FakeLLM

# ============================================================
# 共享测试数据
# ============================================================

SAMPLE_TEXT = """第一章 暴风雪

1969年冬，大兴安岭的暴风雪下了整整三天。红岸基地像一座被世界遗忘的孤岛。

叶文洁裹紧军大衣，推开铁门。寒风如刀，灌入领口。

"叶老师，观测数据出来了。"助手小李递过打印纸。

"谢谢。"叶文洁接过纸张，扫了一眼上面的数字。信号强度在增加。

第二章 信号

深夜，控制室里只剩下叶文洁和仪器运转的蜂鸣声。

突然，示波器跳了一下。她停下手中的笔。

"雷政委！"叶文洁拨通内线，"有情况！"

雷志成很快赶来，领口的扣子都没系。"小叶，你确定不是设备故障？"

叶文洁摇头，"太稳定了。不可能是自然现象。"她的声音在发抖。

两人对视。在这个与世隔绝的山顶基地里，他们第一次感到了真正的恐惧。
"""


# ============================================================
# 真实 LLM 守卫
# ============================================================

class ForbiddenRealLLM:
    """
    一旦被实例化就抛错的 `LLMClient` 替身。

    注入点是 `backend.routes.LLMClient`（routes.py 里 `from backend.llm_client import
    LLMClient`，随后在 `get_llm()` 中实例化），因此：

    - 用例**没有**替换 `backend.routes.get_llm` 时 → 真的会走到这里 → 快速失败，
      既不会联网，也不会悄悄花掉 API 额度；
    - 用例替换了 `get_llm`（如注入 FakeLLM）→ 本类根本不会被碰到，
      与 fixture 的建立顺序无关——这一点比「把 get_llm 换成抛错函数」更健壮，
      后者容易被「谁先 setup」的次序问题搞成假绿；
    - `tests/e2e/test_pipeline_real_llm.py` 直接从 `backend.llm_client` 构造
      `LLMClient`，走的是真实调用，不受本守卫影响。
    """

    def __init__(self, *args, **kwargs):
        raise RuntimeError(
            "测试禁止构造真实 LLMClient（会联网并消耗 API 额度）。"
            "请改用 tests.fakes.FakeLLM；确需真实调用请给用例加 @pytest.mark.llm。"
        )


# ============================================================
# fixture
# ============================================================

@pytest.fixture
def sample_text() -> str:
    """三体「红岸基地」节选——所有层共用的最小可用输入（≥100 字符，满足 ConvertRequest 约束）"""
    return SAMPLE_TEXT


@pytest.fixture
def api_db(tmp_path, monkeypatch):
    """
    把 `DB_PATH` 指向本次用例专属的临时库并建好表结构。

    `backend/database.py` 的 `DB_PATH` 是模块级常量，默认指向项目根的
    `looploop.db`。不隔离的话，每次跑 API 测试都会往**真实任务历史表**写数据。
    database 里的函数都在调用时才读模块级 `DB_PATH`，而 routes.py 导入的是函数
    对象本身，因此只 patch 常量即可全局生效。
    """
    db_path = tmp_path / "looploop_test.db"
    monkeypatch.setattr("backend.database.DB_PATH", db_path)

    asyncio.run(init_db())

    return db_path


@pytest.fixture
def isolate_external_deps(monkeypatch):
    """
    封死真实 LLM，并清空路由层的懒加载单例与事件总线。

    单例（_llm / _pipeline / _parser）与 NOTIFICATION_BUS 都是模块级可变全局，
    不重置会让上一个用例的状态漏进下一个用例。
    """
    monkeypatch.setattr("backend.routes.LLMClient", ForbiddenRealLLM)
    monkeypatch.setattr("backend.routes._llm", None)
    monkeypatch.setattr("backend.routes._pipeline", None)
    monkeypatch.setattr("backend.routes._parser", None)
    monkeypatch.setattr("backend.routes.NOTIFICATION_BUS", {})


@pytest.fixture
def client(api_db, isolate_external_deps):
    """
    基于隔离 DB 的 TestClient。

    用 `with` 进入上下文管理器有两个作用：
      1. 走真实 lifespan 启动路径（uvicorn 启动时同样执行它）；
      2. 让 lifespan、所有请求、以及 `asyncio.create_task` 派发的后台任务
         共享**同一个事件循环**——这正是测试 SSE 流所必需的前提，
         否则后台 Pipeline 与流式响应会跑在两个互不相干的 loop 上。
    """
    from backend.main import app

    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture
def fake_llm() -> FakeLLM:
    """每个用例一个全新的 FakeLLM，调用记录互不串味（默认按 prompt 分发）。"""
    return FakeLLM()
