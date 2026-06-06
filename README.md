# Looploop（噜噜）

> AI 短剧全自动管线 —— 将小说转化为结构化导演指令

Looploop 不是传统的"编剧辅助工具"。它的核心创新在于：**每一个 Shot 就是一个完整的视频生成指令**。Schema 里的 `shot_type`、`camera_movement`、`visual_prompt` 三个字段，下游的 Runway 或可灵可以直接消费。

```
小说原文 → Looploop → 结构化 YAML → 视频生成模型 → 成片
              ↑                        ↑
        人能看懂、能编辑          机器可直接执行
```

## 技术架构

```
 React + Vite + Tailwind      FastAPI + Pydantic       DeepSeek API
┌───────────────────────┐   ┌─────────────────────┐   ┌──────────┐
│  可拖拽面板工作台       │◄─►│  Pipeline 转换引擎   │◄─►│  LLM     │
│  - 左侧: 历史+导航+详情 │   │  - 7 步流水线        │   │          │
│  - 右侧上: 分镜卡片流   │   │  - 角色消歧          │   └──────────┘
│  - 右侧下: 通栏原文面板  │   │  - Pydantic 自我修正  │
│  - 双击编辑+单镜头重刷   │   │  - SQLite 持久化      │
│  - C/S/P 素材编号+Timeline│   │  - 增量角色消歧       │
│  - YAML/Word 导出      │   └─────────────────────┘
└───────────────────────┘
```

## 界面布局

```
┌──────────┬────────────────────────────────────────┐
│ 左侧面板  │           右侧主工作区                   │
│ (可拖拽)  │                                        │
│          │  ┌─────────────────────────────────┐   │
│ HISTORY  │  │  Scene 1 · 红岸基地 · 山顶 · 夜  │   │
│ (可折叠)  │  │  ┌─ ShotCard 1 (特写·推进) ───┐ │   │
│          │  │  │ "如果有人在听……请回答。"      │ │   │
│ SHOT     │  │  └────────────────────────────┘ │   │
│ DETAIL   │  │  ┌─ ShotCard 2 (远景·固定) ───┐ │   │
│          │  │  │ "雷达有异常。"              │ │   │
│ SCENES   │  │  └────────────────────────────┘ │   │
│ · s01    │  └─────────────────────────────────┘   │
│ · s02    │                                        │
│          ├────────────────────────────────────────┤
│ 角色+统计 │  SOURCE TEXT (原文对照) · 可垂直拖拽      │
│ 叶文洁    │  "1969年冬, 大兴安岭的暴风雪..."         │
│ 雷志成    │                                        │
└──────────┴────────────────────────────────────────┘
```

## 快速开始

### 环境要求
- Python ≥ 3.11
- Node.js ≥ 18
- DeepSeek API Key（或任意 OpenAI 兼容的 API）

### 安装启动

```bash
# 1. 克隆仓库
git clone https://github.com/cracbrace/Looploop.git
cd Looploop

# 2. 配置 API Key
cp .env.example .env
# 编辑 .env，填入 LLM_API_KEY

# 3. 创建 Python 环境并安装依赖
python -m venv .venv
source .venv/Scripts/activate  # Windows
pip install -r backend/requirements.txt

# 4. 启动后端（终端 1）
uvicorn backend.main:app --port 8000 --reload

# 5. 启动前端（终端 2）
cd frontend
npm install
npm run dev

# 6. 打开浏览器访问 http://localhost:5173
```

### 使用流程

1. **粘贴小说**：在输入框中粘贴 3 章以上小说文本（可用 `examples/sample_novel.txt`）
2. **开始转换**：点击 "Convert"，实时查看 Pipeline 进度（SSE 流式推送）
3. **浏览结果**：左侧导航切换场景，中央分镜卡片流展示所有镜头
4. **原文联动**：点击任意镜头卡片，底部通栏原文面板自动高亮对应段落
5. **内联编辑**：双击卡片上任意字段（台词、情绪、visual_prompt 等）直接修改，自动持久化
6. **单镜头重刷**：点击卡片上的 ↻ 按钮，输入修改意见，AI 局部重新生成
7. **历史回溯**：左侧 History 面板加载过往转换结果（SQLite 持久化，重启不丢失）
8. **面板拖拽**：所有面板分隔条可拖拽调整尺寸，适配不同工作习惯
9. **Timeline 时间轴**：每个 Shot 自动生成 `0-3s: ... / 3-8s: ...` 分段描述
10. **导出**：Export → All in One (.zip) / YAML / Manifest (C/S/P) / Word

## 核心功能

| 功能 | 说明 | 技术亮点 |
|------|------|----------|
| **Pipeline 转换** | 小说 → 7 步流水线 → YAML 剧本 | 并发逐段提取、两阶段角色消歧 |
| **角色消歧** | "王队长"="老王"="王建国" | LLM 语义聚类 + 规则合并 |
| **分镜卡片** | Shot 级别可视化，景别色条+对白高亮 | 8 种景别颜色编码 |
| **原文联动** | 点击镜头 → 通栏原文段落高亮 | source_paragraphs 溯源索引 |
| **内联编辑** | 双击任意字段直接修改 | EditableField + PATCH API 自动保存 |
| **单镜头重刷** | Human-in-the-loop 局部重新生成 | 异步后端 + 前端局部状态更新 |
| **历史记录** | 过往转换可回溯、可删除 | SQLite 持久化 |
| **可拖拽面板** | 左右/上下分隔条均可拖拽调整 | 像素级 clamp 硬限幅 |
| **自我修正** | LLM 输出不合法 → 自动重试 | Pydantic 校验 + 错误喂回 LLM |
| **素材编号 (C/S/P)** | C01/S01 人可读编号，下游 @C01 引用 | material_id + manifest 导出 |
| **Timeline 时间轴** | 镜头内秒级分段：0-3s/3-8s 动态描述 | LLM 推演 + fallback 自动合成 |
| **运镜情绪提示** | Hover 标签显示英文名+情绪+使用场景 | 11 种 camera_movement 完整字典 |

## YAML Schema

详见 [`docs/YAML_Schema_Design.md`](docs/YAML_Schema_Design.md)

```yaml
meta: { title: "红岸", version: "v0.4" }
characters:
  - material_id: "C01"       # 🆕 v0.4: 人可读素材编号
    canonical_name: "叶文洁"
scenes:
  - material_id: "S01"
    shots:
      - shot_type: "特写"
        camera_movement: "推进"
        visual_prompt: "Close-up of a young woman..."
        timeline:             # 🆕 v0.4: 镜头内时间轴分段
          - "0-3s: 远景建立场景"
          - "3-8s: 推进至近景"
        dialogue: { character: "叶文洁", line: "...", emotion: "孤独" }
```

## 项目结构

```
looploop/
├── backend/
│   ├── main.py              # FastAPI 入口 + lifespan
│   ├── config.py            # pydantic-settings 配置
│   ├── models.py            # Pydantic 数据模型 (Screenplay/Shot/...)
│   ├── llm_client.py        # LLM API 封装 (OpenAI SDK 兼容 DeepSeek)
│   ├── database.py          # SQLite 持久化 (aiosqlite)
│   ├── safe_parser.py       # Pydantic 校验 + LLM 自我修正
│   ├── routes.py            # REST API (转换/SSE/导出/历史/编辑)
│   ├── test_pipeline.py     # 4 层 143 项测试
│   └── engine/
│       ├── pipeline.py          # 7 步 Pipeline 编排
│       ├── text_splitter.py     # 滑动窗口文本切分
│       ├── extractor.py         # LLM 逐段提取 (导演视角 prompt)
│       ├── character_resolver.py # 角色消歧 (别名合并)
│       ├── scene_merger.py      # 场景合并 + Screenplay 组装
│       └── quality_checker.py   # 10+ 条自动质检规则
├── frontend/
│   └── src/
│       ├── App.tsx              # 可拖拽面板主布局
│       ├── types/screenplay.ts  # TS 类型 (与 Pydantic 对应)
│       ├── api/client.ts        # API 客户端 (fetch/SSE/CRUD)
│       ├── hooks/useScreenplay.ts # 核心状态管理 hook
│       └── components/
│           ├── ShotCard.tsx      # 镜头卡片 (可编辑)
│           ├── Sidebar.tsx       # 场景/角色导航
│           ├── HistoryPanel.tsx  # 历史记录面板
│           └── SourcePanel.tsx   # 原文对照面板
├── docs/
│   ├── YAML_Schema_Design.md    # Schema 设计文档
│   └── Testing_Lessons.md       # 测试经验总结
├── examples/
│   └── sample_novel.txt         # 示例小说 (3 章)
└── README.md
```

## 技术栈

| 层 | 技术 | 理由 |
|----|------|------|
| 前端 | React 18 + Vite + Tailwind CSS 4 | 组件化、热更新、原子化 CSS |
| 布局 | 自定义像素拖拽 | 硬限幅 clamp(240, x, 500)，无第三方依赖 |
| 后端 | FastAPI + Uvicorn | 原生 async、自动 Swagger、Pydantic 集成 |
| 数据校验 | Pydantic 2 | 强类型、贯穿全栈的单一真相源 |
| 数据库 | SQLite + aiosqlite | 零配置、异步驱动、重启不丢数据 |
| LLM | DeepSeek API (OpenAI SDK) | 中文强、结构化输出稳、成本低 |
| 导出 | python-docx + PyYAML + zipfile | Zip / Manifest / YAML / Word |

## 设计文档

- [YAML Schema 设计文档](docs/YAML_Schema_Design.md) — 字段详解 + 设计取舍 + v0.4 演进（第 8 章）
- [测试经验总结](docs/Testing_Lessons.md) — Bug 根因分析 + 分层测试策略

## 版本记录

| 版本 | 日期 | 核心变更 |
|------|------|----------|
| v0.4.0 | 2026-06-06 | C/S/P 素材编号体系、Timeline 时间轴、运镜情绪提示、多文件 Zip 导出 |
| v0.3.0 | 2026-06-05 | tiktoken 精准计数、增量角色消歧、SSE 日志流、文件拖拽 |
| v0.2.0 | 2026-06-05 | SQLite 持久化、可拖拽面板、内联编辑、历史记录 |
| v0.1.0 | 2026-06-05 | 核心 Pipeline、Pydantic 模型、基本 UI |

## License

MIT
