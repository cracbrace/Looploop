# Looploop 性能测试基线

> 第一轮自动化基线：2026-10-18。替代 `automated_runner.py` 的「跑完肉眼看输出」模式，
> 产出可复跑的 CSV 与 P50/P95/失败率指标。

## 这个基线度量什么、不度量什么

**度量**：`POST /api/convert` 的**接口受理路径** —— 参数校验、写库、派发后台任务、返回 task_id；
以及 `GET /api/health`、`GET /api/tasks` 两个前端轮询接口。

**不度量**：端到端转换时长（切分 → 逐段提取 → 角色消歧 → 合并 → 落库）。
那一段的耗时几乎全部来自 LLM，需要真实 API key，且每次请求都产生费用。
因此压测一律以**离线模式**启动后端（`LLM_API_KEY` 置空），后台 Pipeline 会快速失败 —
这也恰好让「受理路径」的耗时不被 LLM 噪声污染，测出来的数字更稳定、可比较。

## 环境

| 项 | 值 |
|---|---|
| 机器 | 本机开发机（Windows，单进程 uvicorn） |
| Python | 3.13.12 |
| 依赖 | fastapi 0.136 / uvicorn 0.49 / aiosqlite 0.22 |
| 后端启动 | 离线模式（`LLM_API_KEY=""`），`host=127.0.0.1` |
| 压测工具 | Locust 2.46.7 |
| 数据 | `examples/sample_novel.txt`（截 600 字符）+ `stress_files/` 三份（最大 220 KB） |

## 运行方式

```bash
# 1) 离线启动后端（避免压测触发真实 LLM 调用）
#    用带 LLM_API_KEY="" 的启动器，或先 export LLM_API_KEY= 再 uvicorn
uvicorn backend.main:app --port 8000

# 2) 压测（10 并发 / 每秒起 2 个 / 30 秒）
locust -f locustfile.py --headless -u 10 -r 2 -t 30s --csv=perf_results

# 3) 看结果
#    perf_results_stats.csv            各接口的 P50/P95/失败率
#    perf_results_stats_history.csv    时间序列（可画图）
#    perf_results_failures.csv         失败明细（为空说明 0 失败）
```

`locustfile.py` 定义了两个场景：

- **ConvertUser**（权重 3）：短文本提交 : 重素材提交 = 5 : 1，`wait_time=constant(1)`
- **ReadUser**（权重 2）：`/api/health` : `/api/tasks` = 3 : 1

## 第一轮基线（u=10, r=2, 30s）

| 接口 | 请求数 | 失败 | P50 | P95 | 平均 |
|---|---:|---:|---:|---:|---:|
| `GET /api/health` | 79 | 0 | 6 ms | 14 ms | 7 ms |
| `GET /api/tasks` | 33 | 0 | 20 ms | 30 ms | 20 ms |
| `POST /api/convert [short]` | 132 | 0 | 52 ms | 73 ms | 53 ms |
| `POST /api/convert [stress]` | 26 | 0 | 150 ms | 180 ms | 120 ms |
| **聚合** | **270** | **0 (0.00%)** | **46 ms** | **150 ms** | **42 ms** |

吞吐约 **9.05 req/s**（10 并发 × `wait_time=1s` 的理论上限附近）。

读法：

- `convert [stress]` 的 P50 是 `[short]` 的近 3 倍，说明**请求体大小是受理路径的主要成本**
  （220 KB 素材的 JSON 反序列化 + 写 `original_text` 落库）。
- `/api/tasks` 比 `/api/health` 慢一个量级（20 ms vs 6 ms）—— 前者要开 SQLite 连接并查询，
  后者是纯内存返回。这是当前最值得优化的点（连接复用/池化）。
- 全程 0 失败，说明 10 并发远未触及瓶颈。

## 与既有压测材料的关系

| 材料 | 性质 | 与本文件的关系 |
|---|---|---|
| `automated_runner.py` | 手写脚本 + 打印输出 | 本文件是它的工程化替代：指标落 CSV、场景可调、可进 CI |
| `docs/v045_Stress_Test_Report.md` | 手工记录的三轮对比 | 历史手工报告，保留作演进记录 |
| `docs/v050_Stress_Test_Report.md` | 手工记录的终版矩阵 | 同上 |

> 注意：历史报告里的数字包含**真实 LLM 调用**的耗时，与本文件的「受理路径」基线
> **不可直接比较** —— 量级差异来自被测对象不同，不是性能退化。

## 复跑与变异验证

```bash
# 复跑基线
locust -f locustfile.py --headless -u 10 -r 2 -t 30s --csv=perf_results

# 确认失败率统计真的在工作（变异验证）：
# 把 locustfile.py 里 ConvertUser 的路径改成 /api/nope，重跑
locust -f locustfile.py --headless -u 3 -r 1 -t 5s --csv=perf_bad
# 期望：perf_bad_stats.csv 的 Failure Count 全部 > 0（说明失败被计入，不是恒 0）
```

## 下一轮要压什么

1. **提高并发找拐点**：`-u 50 / 100 / 200`，观察 P95 与失败率何时开始劣化
2. **`/api/tasks` 的库连接开销**：当前每次请求开一个 aiosqlite 连接，是最大疑点
3. **端到端链路**（需真实 key）：`提交 → SSE done` 的完成时长，单独跑、低并发
