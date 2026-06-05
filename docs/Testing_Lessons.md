# Looploop 测试经验总结

> 记录两次端到端 bug 的根因分析与测试改进策略

---

## 1. 两次 Bug 回顾

### Bug 1：`ResolvedCharacter` 无 `.get()` 方法

**报错**：`'ResolvedCharacter' object has no attribute 'get'`

**根因**：`extractor.py` 的 `_build_extraction_prompt()` 中，对 character_registry 的每个值先调用了 `.get()`（dict 方法），再判断 `isinstance(char, dict)`。当值是 `ResolvedCharacter` dataclass 时，`.get()` 不存在。

**为什么测试没抓到**：`test_character_merge` 只验证了 `ResolvedCharacter` 的数据结构本身（别名列表、字段值），从未将 registry 传入 extractor 做联合测试。

**代码路径**：
```
Pipeline.run()
  → CharacterResolver.resolve()  ✅ 单独测试过
  → ChapterExtractor.extract(character_registry=...)  ❌ 联合路径从未测试
    → _build_extraction_prompt()  ← Bug 位置
```

### Bug 2：Meta 空字符串

**报错**：`Meta.title: String should have at least 1 character (input_value='')`

**根因**：`scene_merger.py` 的 `build_screenplay()` 在用户未提供 meta_overrides 时，使用空字符串 `""` 作为 title/source/author/genre 的默认值。Pydantic `Field(min_length=1)` 校验拒绝空字符串。

**为什么测试没抓到**：`test_yaml_output` 直接构造了一个完整的 `Screenplay(dict)` 对象，title="测试"——完美绕过了 `build_screenplay()` 中的默认值逻辑。

**代码路径**：
```
Pipeline.run()
  → SceneMerger.build_screenplay(meta_overrides=None)  ❌ 从未测试
    → meta_data = {"title": "", ...}  ← Bug 位置
  → Screenplay(**meta_data)  ← Pydantic 校验报错
```

---

## 2. 根因：测试了叶子节点，没测数据流

```
现有测试的结构：

  test_text_splitter()      → 单独测试 Splitter
  test_paragraph_mapping()  → 单独测试映射
  test_yaml_output()        → 构造完美 Screenplay → 测序列化
  test_shot_validation()    → 构造单个 Shot → 测校验
  test_character_merge()    → 构造 registry → 测结构

缺失的测试：

  Pipeline.run() 全链路      → 模拟用户输入 → 得到完整输出
  Extractor + Registry       → registry 作为参数传入 extractor
  build_screenplay() 默认值  → meta_overrides=None 的路径
  API POST /api/convert      → 前端实际发送的请求
```

**本质**：每个测试都给自己构造了"完美输入"，从未让真实数据穿过模块边界。

---

## 3. 测试分层原则

```
┌─────────────────────────────────────────────┐
│ Layer 4: API 集成                           │
│  TestClient → POST /api/convert → 轮询结果   │
│  覆盖：路由、序列化、状态码、超时             │
├─────────────────────────────────────────────┤
│ Layer 3: Pipeline 端到端                    │
│  Pipeline.run(sample_novel) → Screenplay    │
│  覆盖：所有模块的联调、默认值、空值处理       │
│  使用：真实 LLM API                          │
├─────────────────────────────────────────────┤
│ Layer 2: 模块集成                           │
│  模块 A + 模块 B 的联合调用                   │
│  覆盖：类型不匹配、接口契约、中间数据格式      │
│  使用：真实模块 + Mock LLM（可选）            │
├─────────────────────────────────────────────┤
│ Layer 1: 单元测试                           │
│  单个函数的输入/输出边界                      │
│  覆盖：参数校验、边界值、空输入、异常路径      │
│  使用：Mock 所有依赖                          │
└─────────────────────────────────────────────┘
```

### 各层的价值

| 层级 | 发现 bug 类型 | 运行速度 | 维护成本 |
|------|-------------|:---:|:---:|
| Layer 1 单元 | 逻辑错误、边界条件 | 毫秒 | 低 |
| Layer 2 集成 | 类型不匹配、接口契约违反 | 秒 | 中 |
| Layer 3 E2E | 默认值缺失、模块交互 | 分钟 | 中 |
| Layer 4 API | 序列化、HTTP 状态 | 分钟 | 低 |

---

## 4. 关键经验

### 4.1 每个公开函数至少两个测试：正常 + 异常

```python
# ❌ 只测正常路径
def test_build_screenplay():
    sp = merger.build_screenplay(scenes, registry, {"title": "测试"})
    assert sp.meta.title == "测试"

# ✅ 正常 + 异常
def test_build_screenplay_with_meta(): ...
def test_build_screenplay_without_meta():  # ← Bug 2 能在这里抓到
    sp = merger.build_screenplay(scenes, registry)  # meta_overrides=None
    assert sp.meta.title != ""
```

### 4.2 测试数据不要全用手工构造

```python
# ❌ 全是手工构造的完美数据
sp = Screenplay(meta=Meta(title="测试", ...), ...)

# ✅ 至少一条测试跑真实函数产出
sp = await pipeline.run(open("sample_novel.txt").read())
```

### 4.3 模块间接口要测"真实类型"

```python
# ❌ 测试用了 dict 代替真实对象
registry = {"char_000": {"canonical_name": "叶文洁", ...}}  # dict!
extractor.extract(text, character_registry=registry)

# ✅ 测试用真实产出类型
resolver = CharacterResolver(llm)
registry = await resolver.resolve(text)  # 真实的 ResolvedCharacter 对象
extractor.extract(text, character_registry=registry)  # ← Bug 1 能在这里抓到
```

### 4.4 每个 if-else 分支都要覆盖

```python
# build_screenplay 有两个分支：
#   if meta_overrides:  meta_data.update(meta_overrides)
#   else:               使用默认值
# 测试只覆盖了 if 分支，else 分支从未执行 → Bug 2 漏过
```

---

## 5. 改进后的测试清单

| # | 测试 | 层级 | 覆盖的 Bug 类型 |
|---|------|:---:|----------------|
| 1 | TextSplitter 切分 + 章节识别 | L1 单元 | 切分逻辑 |
| 2 | TextSplitter 空输入 / 极短输入 | L1 单元 | 边界条件 |
| 3 | Shot Pydantic 合法构造 | L1 单元 | 校验规则 |
| 4 | Shot Pydantic 非法值拦截 | L1 单元 | 校验规则 |
| 5 | Scene 空 shots 拦截 | L1 单元 | 校验规则 |
| 6 | Screenplay YAML 序列化 | L1 单元 | 序列化 |
| 7 | CharacterResolver 别名消歧 | L2 集成 | 消歧逻辑 |
| 8 | **Extractor + Registry 联合调用** | **L2 集成** | **Bug 1 类型** |
| 9 | **build_screenplay 无 meta_overrides** | **L2 集成** | **Bug 2 类型** |
| 10 | **Pipeline.run() 端到端（真实 LLM）** | **L3 E2E** | **数据流全链路** |
| 11 | Pipeline 空文本拒绝 | L3 E2E | 边界条件 |
| 12 | **POST /api/convert 全链路** | **L4 API** | **前后端集成** |
| 13 | GET /api/health 健康检查 | L4 API | 基础连通 |
| 14 | 导出 YAML/Word 端点 | L4 API | 导出功能 |

> 加粗项为本次 Bug 暴露后新增的测试。

---

## 6. 总结

> **不要只测你写好的代码能不能跑。要测它会不会在你不看的时候崩。**
>
> 两条路径最有价值：(1) 端到端跑一次真实数据；(2) 每个模块的默认值 / 空值 / None 分支至少触发一次。
