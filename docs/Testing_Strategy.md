# Looploop 测试策略

> 本文是测试体系的**总纲**：分几层、每层的职责与边界、替身与隔离怎么做、
> 覆盖率与门禁、变异测试方法、CI 现状、已知缺口。
>
> 具体踩坑与根因分析见 [测试经验总结](Testing_Lessons.md)；
> 性能基线见 [Perf_Baseline](Perf_Baseline.md)。

---

## 1. 为什么这样分层

一句话原则：**越靠下越便宜、越靠上越可信**。所以同一条行为，能在低层验证就不放到高层。

| 层 | 目录 | 用例数 | 依赖 | 单次耗时 | 负责回答的问题 |
|---|---|---:|---|---:|---|
| L1 单元 | `tests/unit` | 19 | 无 | <1s | 这个纯函数/模型对不对？ |
| L2 模块集成 | `tests/integration` | 18 | 无 | ~1s | 两个模块拼起来语义对不对？ |
| L4 HTTP 接口 | `tests/api` | 78 | TestClient / 真 uvicorn | ~6s | 接口契约、状态码、响应体对不对？ |
| L3 端到端 | `tests/e2e` | 16（10 个需真实 key） | 全栈 + Pipeline | 6s / 数分钟 | 整条链路能不能跑通？ |

离线全量（`pytest -m "not llm"`）：**120 passed / 3 xfailed / 10 deselected，约 9 秒**。

> 计数说明：`--collect-only` 的参数化计法与运行时统计可能相差 1-2 个，以运行时输出为准。

分层不是目的，**是为了让失败信息指向明确**：L1 红了说明某个函数坏了，L4 红了说明契约变了。
如果所有断言都堆在 L3，一次失败你得从 LLM 输出倒推十几层。

---

## 2. 每层的边界（什么时候**不要**往下放）

| 想验证的东西 | 该放 | 不该放 |
|---|---|---|
| `normalize_text` 的段落切分规则 | L1 | L3（要真 LLM，慢且不稳定） |
| SceneMerger 的时长合并策略 | L2 | L4（接口层看不到这个细节） |
| `/api/tasks` 的字段与状态码 | L4 | L1（那是 HTTP 契约，不是函数行为） |
| 「提交 → 进度 → 分镜渲染」整链路 | L3 | L1（跨了十几层，纯函数测不出来） |
| SSE 的**增量投递**与心跳 | L4 + 真 uvicorn | L4 用 TestClient（见 §5） |

两条硬规则：

1. **不测实现，测契约**。断言 `task_id` 是 12 位 hex，而不是断言内部调了哪个函数。
2. **同一个行为不重复测**。L1 已覆盖的解析逻辑，L4 不再重复；L4 只验「这层自己引入的东西」
   （序列化、状态码、路由、依赖注入）。

---

## 3. 替身与隔离

### FakeLLM（`tests/fakes/fake_llm.py`）

离线全链路的基石。两种用法：

```python
# 1) prompt marker 分派：按提示词里的标记返回对应形状的响应
fake = FakeLLM()                      # 内部按 "请修正" / "merge_groups" / "characters_found" 分派

# 2) 脚本回放：按顺序返回预设响应，用于多轮/重试路径
fake = FakeLLM(responses=[bad_json, good_json])

# 3) 静默：让 SSE 流真的"安静"若干秒，用于测心跳
fake = FakeLLM(delay_seconds=1.5)
```

未知提示词会**直接 `AssertionError`** —— 这是刻意的：宁可测试报错，也不要悄悄返回一个
让人误以为通过的默认值。

### 数据库隔离

`tests/conftest.py` 的 `api_db` 把 `backend.database.DB_PATH` monkeypatch 到 `tmp_path`。
跑完测试，项目根的 `looploop.db` 一个字节都不会变。

### 真实依赖守卫

`isolate_external_deps` 用 `ForbiddenRealLLM` 替换 `backend.routes.LLMClient`。
一旦某个用例意外走到真实 LLM 分支，会立刻炸而不是产生费用。

> 为什么需要这个守卫：`.env` 里有真实 key。没有守卫的话，一次疏忽就会真的调 API，
> 而且测试**仍然通过**（只是慢了几十秒、账单多了几毛），这种静默成本最难发现。

---

## 4. 覆盖率基线与门禁

| 端 | 度量 | 基线 | 门禁 | 门禁位置 |
|---|---|---|---|---|
| 后端 | pytest-cov | **69%** | 65% | CI（`--cov-fail-under=65`） |
| 前端 | vitest v8 | **47.09 / 33.67 / 35.5 / 53.7** | 45 / 32 / 33 / 51 | `vitest.config.ts` |

后端亮点：`routes.py` 99%、`extractor.py` 100%、`database.py` 95%。
后端短板：`quality_checker.py` **0%**、`llm_client.py` 18%（网络调用）、
`character_resolver.py` 41%、`safe_parser.py` 48%。

**后端的门禁为什么不写进 `pytest.ini`**：`--cov-fail-under` 对*任意一次*运行生效，
于是 `pytest tests/unit`（单层调试）和 `pytest tests/e2e`（真实 LLM，仅 12 例）
都会因为「只跑了一部分」而跌破阈值直接失败，把 README 里记录的命令全部搞坏。
所以后端把门禁放在 CI 的整跑命令上；本地需要时显式加 `--cov-fail-under=65`。

**前端可以写进配置**，因为 `npm test` 永远是全量。

### `quality_checker.py` 为什么是 0%

全仓库 grep 下来，除了它自己的 `class QualityChecker` 定义，**没有任何地方 import 它**。
这是 `CLAUDE.md`「PR 计划执行完整性检查」那条教训的机器化复现：
PR #11 提交了质检模块，但 PR #10 的路由跳过了 `/report` 端点，模块成了未接入的孤岛。
覆盖率这次独立地验证了这个结论 —— 它不只是个百分比，还是发现死代码的手段。

---

## 5. SSE 测试的反模式（本项目踩过）

**反模式**：用 `TestClient` 断言「事件是一个个到达的」。

`TestClient` 会把整个响应体缓冲完再交给你，所以「增量」这件事在它下面**根本不可观测** ——
写出来的断言永远是假的（无论代码怎么改都通过）。而且如果生成器意外不终止，
它会一直阻塞在读响应体上（实测挂死 300s，而测试内部的任何 deadline 检查都执行不到）。

**正确做法**：拆成两类断言。

| 断言什么 | 用什么 | 为什么 |
|---|---|---|
| 事件内容与顺序、终态、404 | `TestClient` | 缓冲不影响内容断言 |
| **增量投递**、15s 心跳 | `live_server`（真 uvicorn 线程，端口 0） | 只有真 HTTP 才能观察到「先到 A 后到 B」和「静默期内有心跳」 |

配套兜底：`pytest.ini` 里 `timeout = 90` + `timeout_method = thread`，
把「挂死」压成「失败」，避免 CI job 一路挂到 6 小时上限。

---

## 6. 前端测试

| 工具 | 用途 | 位置 |
|---|---|---|
| Vitest + jsdom | 单元/组件测试 | `frontend/src/**/*.test.tsx` |
| Testing Library | 以用户视角查询 DOM（而非实现细节） | 同上 |
| Playwright | 真浏览器 E2E（不启后端，`page.route` 拦截 `/api/**`） | `frontend/e2e/` |

三个刻意的决定：

1. **`vitest.config.ts` 与 `playwright.config.ts` 独立存在，不改 `vite.config.ts`**。
   测试的关注点（jsdom、setupFiles、include 范围、webServer）不该污染生产构建配置。
2. **测试文件用显式 import**（`import { describe } from "vitest"`），不往 tsconfig 注入
   `vitest/globals` 类型。这样 `tsc -b` 在 `include: ["src"]` 下能正常类型检查测试代码，
   应用的类型环境保持干净。
3. **fixture 用 `satisfies` 而非 `as`**（`src/test/fixtures.ts`）。
   字段写错/写漏时 `tsc -b` 直接报错 —— 实际就抓到过一次：
   `Shot.dialogue` 的类型是 `Dialogue | undefined`，用例里写 `null` 会被当场拒掉。

E2E 的边界：**只验前端集成，不启后端**。所有 `/api/**` 由 `page.route` 拦截并回 fixture，
所以它不需要 API key、不产生费用、在 CI 里也可以放心跑。

---

## 7. 变异测试（红绿验证）

**为什么要做**：一个用例「通过」不代表它有效。删掉被测逻辑它还能通过，那它就是装饰品。

方法：改一处生产代码 → 跑测试 → **必须变红** → 还原。

本项目的实测记录：

| PR | 突变 | 结果 |
|---|---|---|
| 03 | `_normalize_time_of_day` 的映射改错 | CAUGHT |
| 04 | 列表接口去掉 `status` 字段 | CAUGHT |
| 04 | 404 分支去掉 `raise HTTPException` | CAUGHT |
| 10 | SSE 心跳间隔常量改成 3600s | CAUGHT |
| 14 | `fetchHistory` 的 URL 拼错（`/tasks`→`/taks`） | CAUGHT |
| 14 | `convertNovel` 返回 `data.id` 而非 `data.task_id` | CAUGHT |
| 15 | 失败链不再 `setStatus("error")` | CAUGHT |
| 15 | 重刷把整场镜头替换成单只 | CAUGHT |
| 16 | ShotCard 删掉 `onClick` 调用 | CAUGHT |
| 16 | SourcePanel 高亮条件取反 | CAUGHT |
| 17 | 分镜卡片 map 改成空数组 | CAUGHT |
| 19 | 移走 hook 测试文件 → 覆盖率跌破阈值 | CAUGHT |
| 20 | 改 locust 路径为 `/api/nope` → 失败率上升 | CAUGHT |

也遇到过**无效突变**（属于测试方法本身的问题，不是漏网）：

- `JSON.parse(line.slice(6))` → `slice(5)`：`JSON.parse` 容忍前导空白，语义等价，所以不该变红。

### 已知未覆盖（留档）

| 位置 | 行为 |
|---|---|
| `SceneMerger._merge_duration` | 场景级时长合并 |
| `SceneMerger._normalize_time_of_day` | 时间归一化（部分已被 L2 间接覆盖） |
| `Extractor._parse_response` 的 `globalize()` | 段落索引全局偏移 |

---

## 8. 性能测试

见 [Perf_Baseline](Perf_Baseline.md)。要点：`locustfile.py` 度量的是**接口受理路径**
（校验 + 写库 + 派发），不含 LLM；压测必须以离线模式启动后端，否则每次请求都真调 API。

---

## 9. CI 现状

两个 workflow，均已在 GitHub Actions 实跑通过。

| Workflow | 触发 | 内容 | 实跑 |
|---|---|---|---|
| `backend.yml` | push / PR / dispatch | `pytest -m "not llm" --cov-fail-under=65` + 上传 `coverage.xml` | 30-35s，success |
| `frontend.yml` | push / PR / dispatch | `npm ci` → `lint`(非阻塞) → `test --coverage` → `build` | ~25s，success |

两处刻意的不阻塞：

- **前端 lint 非阻塞**：main 上已有 39 个 `@typescript-eslint/no-explicit-any`，
  属历史债。不让它把整条 CI 常年染红；清理完这批 any 后去掉 `continue-on-error` 即变硬门禁。
- **Playwright E2E 暂时不进 CI**：需下载 chromium（~150MB）+ 拉起 dev server，单次 1-2 分钟。
  文件内已注明加进来的两条命令，本地 `npm run test:e2e` 已跑通。

---

## 10. 已知缺陷与 xfail 台账

`strict=True` 的 xfail：**一旦产品侧修好，测试会立刻变红提醒你删掉标记**，不会悄悄留着一份假绿。

| # | 缺陷 | 严重度 | 位置 |
|---|---|---|---|
| 1 | 非 ASCII 标题的 `export/zip` 返回 500（前端「All in One (.zip)」按钮全废） | 高 | `backend/routes.py` |
| 2 | `export/manifest` 在 `material_id` 为空时素材编号塌缩 | 中 | `backend/routes.py` |
| 3 | `PATCH /api/screenplay` 无 schema 校验（坏数据也能写进去） | 中 | `backend/routes.py` |
| 4 | 重刷后的镜头**未持久化**（只改 React state，刷新即丢） | 中 | `frontend/src/App.tsx` 的 `onRegenerate` |

> 第 4 条不在 `useScreenplay` 里 fail —— hook 只负责更新 state，持久化是调用方的职责。
> 若在 hook 层写 xfail，会把问题记到错误的层上。

---

## 11. 新增测试的速查表

```bash
# 后端
pytest -m "not llm" -q                       # 离线全量（日常）
pytest tests/api/test_tasks.py -v            # 单文件
pytest tests/unit -v --no-cov                # 单层（--no-cov 避免覆盖率干扰输出）
pytest -m "not llm" --cov-fail-under=65      # 本地跑门禁
pytest --alluredir=allure-results            # 产出 allure

# 前端
npm test                                     # 全量（含覆盖率阈值）
npm test -- --coverage=false                 # 单文件调试
npm run test:e2e                             # Playwright（不启后端）
npm run build                                # tsc -b + vite build
```

写新用例时的检查清单：

- [ ] 放在**最低可行层**，而不是顺手放 L3
- [ ] 断言的是契约/可观测行为，不是内部调用
- [ ] 需要 LLM 的用例打 `@pytest.mark.llm`
- [ ] 新 fixture 类型用 `satisfies`，不要 `as`
- [ ] 跑一次变异：删掉对应实现，用例**必须变红**
- [ ] 若发现产品缺陷但本次不修，用 `pytest.xfail(strict=True)` 并登记到 §10 的表
