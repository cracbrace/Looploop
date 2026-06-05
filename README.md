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
React + Vite + Tailwind     FastAPI + Pydantic      DeepSeek API
┌──────────────────┐    ┌──────────────────────┐    ┌──────────┐
│  前端剧本工作台    │◄──►│  Pipeline 转换引擎    │◄──►│  LLM     │
│  - 双栏布局       │    │  - 文本切分           │    │          │
│  - 分镜卡片流     │    │  - 逐段提取           │    └──────────┘
│  - 原文联动       │    │  - 角色消歧           │
│  - 单镜头重刷     │    │  - 场景合并           │
│  - YAML/Word导出  │    │  - Pydantic 自我修正   │
└──────────────────┘    └──────────────────────┘
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

# 6. 打开浏览器访问
# http://localhost:5173
```

### 使用流程

1. **粘贴小说**：在输入框中粘贴 3 章以上小说文本（可用 `examples/sample_novel.txt`）
2. **开始转换**：点击"Convert"，实时查看 Pipeline 进度
3. **浏览结果**：左侧场景导航，右侧分镜卡片流
4. **原文联动**：点击任意镜头卡片，底部原文面板自动高亮对应段落
5. **单镜头重刷**：点击卡片上的 ↻ 按钮，输入修改意见，AI 局部重新生成
6. **导出**：Export → YAML（供 AI 管线）/ Word（供编辑阅读）

## 核心功能

| 功能 | 说明 | 技术亮点 |
|------|------|----------|
| **Pipeline 转换** | 小说 → 7 步流水线 → YAML 剧本 | 并发逐段提取、两阶段角色消歧 |
| **角色消歧** | "王队长"="老王"="王建国" | LLM 语义聚类 + 规则合并 |
| **分镜卡片** | Shot 级别的可视化卡片 | 景别色条、对白高亮、选中联动 |
| **原文联动** | 点击镜头 → 原文段落高亮 | source_paragraphs 溯源索引 |
| **单镜头重刷** | Human-in-the-loop 局部重新生成 | 异步后端 + 前端局部状态更新 |
| **自我修正** | LLM 输出不合法 → 自动重试 | Pydantic 校验 + 错误喂回 LLM |

## YAML Schema

详见 [`docs/YAML_Schema_Design.md`](docs/YAML_Schema_Design.md)

快速概览：
```yaml
meta:           # 剧本元信息
characters:     # 全局角色字典（消歧后）
scenes:
  - shots:      # 镜头列表（最小原子）
    - shot_type: "特写"
      camera_movement: "推进"
      visual_prompt: "Close-up of..."
      dialogue: { character, line, emotion }
```

## 项目结构

```
looploop/
├── backend/
│   ├── main.py              # FastAPI 入口
│   ├── config.py            # 配置管理
│   ├── models.py            # Pydantic 数据模型
│   ├── llm_client.py        # LLM API 封装
│   ├── safe_parser.py       # 校验 + 自我修正
│   ├── routes.py            # REST API 路由
│   └── engine/
│       ├── pipeline.py          # Pipeline 编排器
│       ├── text_splitter.py     # 文本切分
│       ├── extractor.py         # 逐段提取
│       ├── character_resolver.py # 角色消歧
│       ├── scene_merger.py      # 场景合并
│       └── quality_checker.py   # 质检报告
├── frontend/
│   └── src/
│       ├── App.tsx              # 主页面（输入/结果/加载三态）
│       ├── types/screenplay.ts  # TypeScript 类型
│       ├── api/client.ts        # API 客户端
│       └── hooks/useScreenplay.ts # 状态管理
├── docs/
│   └── YAML_Schema_Design.md    # Schema 设计文档
├── examples/
│   └── sample_novel.txt         # 示例小说
└── README.md
```

## 技术栈

| 层 | 技术 | 理由 |
|----|------|------|
| 前端 | React 18 + Vite 5 + Tailwind CSS 4 | 开发快、组件化、现代感 |
| 后端 | FastAPI + Uvicorn | 原生 async、自动 API 文档、Pydantic 集成 |
| 数据校验 | Pydantic 2 | 强类型、贯穿全栈的单一真相源 |
| LLM | DeepSeek API（OpenAI SDK 兼容） | 中文能力强、结构化输出稳、成本低 |
| 文档生成 | python-docx | Word 导出 |

## License

MIT
