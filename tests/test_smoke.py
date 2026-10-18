"""
PR 01 smoke 测试。

只证明三件事，不迁移任何旧用例：
  1. 新的 pytest 框架能被发现并运行
  2. backend 包在 rootdir 下可导入（pytest.ini 的 pythonpath = . 生效）
  3. FastAPI 应用能启动到可响应 /api/health

迁移期的验收标准曾是「新旧两套并存互不影响」：
    pytest                          → 本文件全绿
    python backend/test_pipeline.py → 18/18 PASS

PR 02-05 完成 18 个用例的迁移后，PR 07 已删除自研的 `backend/test_pipeline.py`，
**pytest 现在是本项目唯一的测试入口**。
"""

from backend.main import app


def test_app_importable():
    """
    应用对象可导入且元信息正确。

    这个断言同时是 pythonpath 配置的哨兵：若 `from backend.main import app`
    解析失败，收集期就会报错，说明 pytest.ini 的 sys.path 注入没生效。
    """
    assert app is not None
    assert app.title == "Looploop API"


def test_health_endpoint(client):
    """/api/health 返回 200，且 status / app 字段稳定。"""
    resp = client.get("/api/health")

    assert resp.status_code == 200, f"got {resp.status_code}"

    body = resp.json()
    assert body["status"] == "ok", f"got {body}"
    assert body["app"] == "Looploop", f"got {body}"
