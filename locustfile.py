"""
Looploop 性能测试场景（Locust）。

设计说明
--------
本项目转换链路的真实耗时主要来自 LLM，且 `POST /api/convert` 是**受理即返回**
（后台 `asyncio.create_task` 驱动 Pipeline）。因此在本地/CI 里跑压测时，
本文件度量的是「**接口受理路径**」的性能（鉴权、校验、写库、派发），
而不是端到端转换时长 —— 后者需要真实 LLM key，见文末说明。

用法
----
    # 先起后端（离线模式，不消耗 API 额度）
    uvicorn backend.main:app --port 8000

    # 10 并发、每秒起 2 个、跑 30s，结果落 CSV
    locust -f locustfile.py --headless -u 10 -r 2 -t 30s --csv=perf_results

    # 浏览器里点参数
    locust -f locustfile.py --host http://127.0.0.1:8000
"""

from __future__ import annotations

import os
import pathlib
import random

from locust import HttpUser, constant, task

ROOT = pathlib.Path(__file__).resolve().parent
EXAMPLES = ROOT / "examples"
STRESS = ROOT / "stress_files"

#: 短文本冒烟：只取前 600 字符，避免把压测变成带宽测试
SHORT_TEXT = (EXAMPLES / "sample_novel.txt").read_text(encoding="utf-8")[:600]

#: 重量级素材：stress_files/ 下三份（含 220 KB 的边界/逻辑素材）
STRESS_TEXTS = [
    p.read_text(encoding="utf-8") for p in sorted(STRESS.glob("*.txt"))
]


class ConvertUser(HttpUser):
    """
    转换接口的提交压力。

    权重设计：短文本 5 : 重素材 1 —— 重素材单次开销大，权重高了会把
    P95 完全带偏，但它又必须被覆盖，否则测不到大 body 的受理成本。
    """

    host = os.getenv("LOOPLOOP_HOST", "http://127.0.0.1:8000")
    weight = 3
    wait_time = constant(1)

    @task(5)
    def submit_short(self) -> None:
        self._submit(SHORT_TEXT, "short")

    @task(1)
    def submit_stress(self) -> None:
        self._submit(random.choice(STRESS_TEXTS), "stress")

    def _submit(self, text: str, kind: str) -> None:
        name = f"POST /api/convert [{kind}]"
        with self.client.post(
            "/api/convert", json={"text": text}, name=name, catch_response=True
        ) as response:
            if response.status_code != 200:
                response.failure(f"expected 200, got {response.status_code}")
                return
            try:
                task_id = response.json().get("task_id")
            except ValueError:
                response.failure("response is not JSON")
                return
            # 受理成功的唯一判据：拿得到 12 位 hex 的 task_id
            if not isinstance(task_id, str) or len(task_id) != 12:
                response.failure(f"unexpected task_id: {task_id!r}")


class ReadUser(HttpUser):
    """只读接口压力：健康检查与任务列表（前端轮询会打这两个）。"""

    host = os.getenv("LOOPLOOP_HOST", "http://127.0.0.1:8000")
    weight = 2
    wait_time = constant(1)

    @task(3)
    def health(self) -> None:
        self.client.get("/api/health", name="GET /api/health")

    @task(1)
    def list_tasks(self) -> None:
        # 注意：方法名不能叫 tasks —— 会覆盖 Locust 用来登记任务的 `tasks` 类属性，
        # 导致 "TypeError: 'function' object is not iterable"
        self.client.get("/api/tasks", name="GET /api/tasks")


# ---------------------------------------------------------------------------
# 端到端转换时长（需真实 LLM，默认不启用）
#
# 如果要测「提交 → 生成完成」的端到端时长，需要：
#   1. .env 里配置真实 LLM_API_KEY
#   2. 加 --class-picker 或 -c 指定 SseUser，并把并发压到个位数
# 因为每次请求都会真实消耗 API 额度，这里不默认挂载。
# ---------------------------------------------------------------------------
