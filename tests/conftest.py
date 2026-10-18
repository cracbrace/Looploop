"""
Looploop pytest 全局 fixture 与共享测试数据。

分层约定（对应旧 backend/test_pipeline.py 的 L1-L4）：
    tests/unit/          L1 单元      —— 单个函数 / 数据模型的边界
    tests/integration/   L2 模块集成  —— 模块间的数据流与契约
    tests/api/           L4 接口      —— HTTP 端点行为（状态码矩阵 + 响应体格式）
    tests/e2e/           L3 端到端    —— Pipeline 全链路

PR 01 只建立骨架：
  - SAMPLE_TEXT 自 backend/test_pipeline.py 原样搬入，四层共用
  - client 是 FastAPI TestClient 雏形；PR 04 会补齐测试数据库隔离
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

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
# fixture
# ============================================================

@pytest.fixture
def sample_text() -> str:
    """三体「红岸基地」节选——所有层共用的最小可用输入（≥100 字符，满足 ConvertRequest 约束）"""
    return SAMPLE_TEXT


@pytest.fixture
def client() -> TestClient:
    """
    FastAPI 测试客户端（雏形）。

    PR 01 只提供裸 TestClient：/api/health 这类只读端点不依赖 lifespan，
    因此不进入上下文管理器、不触发 init_db()，避免动到真实的 looploop.db。

    PR 04 会把它升级为「隔离 DB + 显式触发 lifespan」的版本，
    届时 tests/api/ 下所有用例自动获得数据库隔离。
    """
    from backend.main import app

    return TestClient(app)
