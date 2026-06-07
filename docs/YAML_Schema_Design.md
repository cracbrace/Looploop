# Looploop YAML Schema 设计文档

> 版本：v0.1.0  
> 日期：2026-06-05  
> 项目：Looploop（噜噜）— AI 短剧全自动管线

---

## 1. 设计背景

### 1.1 问题

小说作者希望将自己的作品改编成剧本，但传统改编依赖专业编剧，成本高、周期长。而 AI 视频生成模型（Runway、可灵等）的出现，为"小说→视频"的全自动管线提供了可能——但管线中缺少一个关键的**中间表示层**。

### 1.2 定位

Looploop YAML Schema 的定位不是"给编剧看的剧本"，而是 **"给 AI 导演执行的指令集"**。

```
小说原文 → Looploop(Schema) → 视频生成模型 → 成片
              ↑
        人能看懂、机器能执行
```

这个 Schema 同时服务两个受众：
- **机器**（下游视频模型）：每个 Shot 是一个完整、可独立执行的渲染指令
- **人**（作者/编辑）：可读可改，支持 Human-in-the-loop

### 1.3 与参考 PDF 的区别

| 维度 | PDF 参考 Schema | Looploop Schema |
|------|:---:|:---:|
| 设计导向 | 人类编剧阅读 | 机器消费优先 + 人类可编辑 |
| 嵌套深度 | 7-8 层 | **3 层**（Meta → Scene → Shot） |
| 镜头语言 | 可选、学术化 | **必填**、生产级枚举值 |
| visual_prompt | 无 | **核心字段**，直接喂给视频模型 |
| 角色管理 | 分散在各场景 | 全局 `characters` 字典，支持消歧 |
| 溯源 | 无 | `source_paragraphs` 支持原文联动 |

---

## 2. 设计原则

### 2.1 Machine-First（机器优先）

Schema 中的每一个字段，都必须回答同一个问题：**下游的视频生成模型能不能直接消费这个字段？**

这决定了：
- `shot_type` 和 `camera_movement` 是必填的——视频模型是"木头"，没有主观能动性，不给运镜指令就输出静态画面
- `visual_prompt` 用英文——当前所有主流 T2V 模型（Runway Gen-3、可灵、Sora）的训练数据以英文为主
- `duration` 用秒数——直接对应视频片段的时长切割

### 2.2 Human-Readable（人可读）

YAML 的选择本身就体现了这一原则——相比 JSON 的花括号和引号，YAML 的缩进结构更接近人类阅读习惯。作者不需要编程背景就能看懂和编辑。

### 2.3 Shot = Render Command（镜头即指令）

Shot 是 Schema 的**最小原子单位**，不是 Scene。原因是：
- 一个视频生成的"素材"是一个镜头，不是一个场景
- 每个 Shot 的 visual_prompt + shot_type + camera_movement 构成一个完整的渲染指令
- Scene 只是 Shot 的逻辑分组（共享时空）

### 2.4 Flat over Deep（扁平优于深层）

最大嵌套深度控制在 3 层：`Screenplay → Scene → Shot → Dialogue`。这保证了：
- 人可快速定位到任意一个镜头或对白
- 编辑时不需要在深层嵌套中跳转
- 下游解析时出错概率更低

### 2.5 Extensible（可扩展）

每个 Shot 携带 `extra` 字典和可选的 `background`、`sfx`、`bgm` 字段。未来可扩展：
- 灯光方案（`lighting_setup`）
- 服装描述（`costume`）
- 特效标记（`vfx`）
- 转场类型（`transition`）

这些扩展只增不改，保持向后兼容。

---

## 3. Schema 结构

### 3.1 三层架构

```
Screenplay
├─ meta           # 层 1：剧本元信息
├─ characters[]   # 层 2：全局角色字典
└─ scenes[]
   └─ shots[]     # 层 3：镜头列表（最小原子）
      └─ dialogue # 可选：对白
```

### 3.2 完整结构图

```
meta:
  title, source, author, genre
  total_scenes, total_shots, total_duration_estimate
  target_platform, language, version

characters:  # 全局字典——角色消歧的核心输出
  - character_id: "char_001"
    canonical_name: "叶文洁"
    aliases: ["叶老师", "小叶"]
    description: "年轻的天体物理学家"
    role_type: protagonist
    gender: female
    age_range: "25-30"

scenes:
  - scene_id: "s01"
    scene_number: 1
    location: "红岸基地 · 山顶"
    time_of_day: night
    atmosphere: "孤独、压抑"
    duration_estimate: "45s"
    source_paragraphs: [0, 1]
    shots:
      - shot_id: "s01_01"
        shot_number: 1
        shot_type: "大远景"
        camera_movement: "缓慢推进"
        focus_subject: "射电望远镜"
        visual_prompt: "A massive radio telescope on a snowy mountain..."
        duration: "5s"
        source_paragraphs: [0]
        dialogue:  # 可选
          character: "叶文洁"
          character_id: "char_001"
          line: "如果有人在听……请回答。"
          emotion: "孤独"
```

---

## 4. 字段详解

### 4.1 Meta 层

| 字段 | 类型 | 必填 | 说明 |
|------|------|:---:|------|
| `title` | string | ✅ | 剧本名称 |
| `source` | string | ✅ | 原著名称 |
| `author` | string | ✅ | 原作者 |
| `genre` | string | ✅ | 类型标签 |
| `total_scenes` | int | ✅ | 场景总数 |
| `total_shots` | int | ✅ | 镜头总数 |
| `total_duration_estimate` | string | ✅ | 预估总时长，如"3min20s" |
| `target_platform` | string | ❌ | 目标平台（抖音短剧/Reelshort等） |
| `language` | string | ❌ | 语言代码，默认"zh-CN" |
| `version` | string | ❌ | Schema 版本号 |

### 4.2 Character 层

| 字段 | 类型 | 必填 | 说明 |
|------|------|:---:|------|
| `character_id` | string | ✅ | 唯一 ID，格式"char_NNN" |
| `canonical_name` | string | ✅ | 规范名称，所有 dialogue 必须使用 |
| `aliases` | [string] | ❌ | 所有别名列表，供消歧用 |
| `description` | string | ✅ | 一句话角色描述 |
| `role_type` | enum | ✅ | protagonist/antagonist/supporting/cameo |
| `gender` | enum | ✅ | male/female/other |
| `age_range` | string | ❌ | 年龄范围，如"25-30" |

**设计考量**：`character_id` 是消歧的核心——当"王队长"在 extractor 中被识别后，resolver 将其映射到 "王建国" 的 `char_002`。后续所有 shot 的 dialogue 都通过 `character_id` 引用，而非裸字符串。

### 4.3 Scene 层

| 字段 | 类型 | 必填 | 说明 |
|------|------|:---:|------|
| `scene_id` | string | ✅ | 唯一 ID，格式"sNN" |
| `scene_number` | int | ✅ | 场景序号 |
| `location` | string | ✅ | 地点描述（可加时间和子地点） |
| `time_of_day` | enum | ✅ | day/night/dawn/dusk/interior |
| `era` | string | ❌ | 时代背景 |
| `atmosphere` | string | ✅ | 情绪氛围 |
| `weather` | string | ❌ | 天气 |
| `duration_estimate` | string | ✅ | 预估场景时长 |
| `source_paragraphs` | [int] | ❌ | 对应原文段落索引 |
| `shots` | [Shot] | ✅ | 镜头列表（≥1 个） |

**设计考量**：`atmosphere` 是必填的——它不是装饰，而是直接指导 video prompt 的氛围基调。`source_paragraphs` 建立了剧本与原文的双向链接。

### 4.4 Shot 层（核心）

| 字段 | 类型 | 必填 | 说明 |
|------|------|:---:|------|
| `shot_id` | string | ✅ | 唯一 ID，格式"sNN_MM" |
| `shot_number` | int | ✅ | 场景内序号 |
| **`shot_type`** | enum | ✅ | **景别**，8 种枚举 |
| **`camera_movement`** | enum | ✅ | **运镜**，11 种枚举 |
| `focus_subject` | string | ✅ | 镜头焦点/主体 |
| **`visual_prompt`** | string | ✅ | **T2V 模型直接输入**，≥20 字符 |
| `background` | string | ❌ | 背景补充 |
| `dialogue` | Dialogue | ❌ | 对白（无对白则为 null） |
| `sfx` | string | ❌ | 音效描述 |
| `bgm` | string | ❌ | 配乐方向 |
| `duration` | string | ✅ | 镜头时长（格式"{n}s"） |
| `source_paragraphs` | [int] | ❌ | 原文段落溯源 |
| `extra` | dict | ❌ | 扩展字段 |

#### 4.4.1 shot_type 枚举

| 值 | 英文 | 画面范围 | 典型用途 |
|----|------|----------|----------|
| `大远景` | Extreme Wide | 环境主导，人物极小 | 建立场景、展现宏大世界观 |
| `远景` | Wide | 人物全身 + 环境 | 角色入场、动作戏 |
| `中景` | Medium | 腰部以上 | 日常对话 |
| `近景` | Close-Up | 胸部以上 | 情感表达、关键台词 |
| `特写` | Extreme CU | 面部或物体细节 | 情绪高潮、关键道具 |
| `大特写` | Macro | 极致细节 | 眼神、微表情 |
| `双人镜头` | Two-Shot | 两人同框 | 对话对峙 |
| `过肩镜头` | OTS | 从背后拍对方 | 主观视角 |

#### 4.4.2 camera_movement 枚举

| 值 | 说明 | 情绪暗示 |
|----|------|----------|
| `固定` | 静止不动 | 冷静观察、对峙 |
| `推进` | 缓慢接近 | 关注、紧张升级 |
| `拉远` | 缓慢远离 | 孤独、离别 |
| `左摇` / `右摇` | 水平转动 | 视线跟随、场景展开 |
| `上摇` / `下摇` | 垂直转动 | 仰视/俯视 |
| `跟随` | 跟踪主体 | 行走、追逐 |
| `环绕` | 环绕旋转 | 戏剧性时刻 |
| `手持` | 模拟晃动 | 紧张、纪实 |
| `快速变焦` | 急速推拉 | 震惊、反转 |

#### 4.4.3 visual_prompt 设计

**为什么是英文？** 当前主流 T2V 模型（Runway Gen-3/Gen-4、可灵 2.0、Sora）的训练数据以英文为主。中文 prompt 也可以工作，但英文 prompt 的画面质量和风格控制力明显更好。

**为什么 ≥20 字符？** 太短的 prompt（如"a man walking"）会让 T2V 模型自由发挥度过高，画面不可控。20 字符是一条基本的信息量底线，实际上推荐 50-100 字符。

**推荐结构**：`[主体 + 动作/状态] + [环境描述] + [光线/色调] + [风格/年代]`

示例：
```
A close-up of a young Chinese woman in a 1970s military coat,
looking up at the starry sky with a mix of wonder and sadness,
cold winter night, warm campfire light on her face,
cinematic, deep blue color grade
```

#### 4.4.4 为什么对白绑定到 Shot 而非 Scene？

在实际拍摄和 AI 视频生成中，对白与镜头是 **1:1 绑定** 的——一个镜头内通常只有一句/一段对白。将对白放在 Scene 层会丢失"这句台词是哪个镜头说的"这一关键信息，导致：
- 下游对口型同步无法精确匹配
- 剪辑时不知道台词对应哪个画面

---

## 5. 设计取舍

### 5.1 为什么选 YAML 而非 JSON？

| 维度 | JSON | YAML |
|------|------|------|
| 人类可读性 | 低（花括号、引号视觉噪音） | 高（缩进结构，接近自然阅读） |
| 作者编辑门槛 | 需要理解 JSON 语法 | 基本不需要学习 |
| 机器解析 | 原生支持 | PyYAML 一行搞定 |
| 注释支持 | 无 | 有（`#` 注释） |
| 多行文本 | 需要 `\n` 转义 | `>` 或 `|` 自然支持 |

对于"作者可以快速获得可编辑的剧本初稿"这个需求，YAML 明显优于 JSON。

### 5.2 为什么 Shot 是最小原子？

如果以 Scene 为最小原子，那么：
- 一个 Scene 包含多句对白和多个动作 → T2V 模型没法一次性生成复杂叙事
- 对白和画面不对应 → 剪辑时找不到"这张嘴说话"的画面

**Shot 作为最小原子的代价**：Schema 行数更多（一个场景 5-10 个 shot）
**收益**：每个 shot 可独立渲染；对白精确配准；镜头语言可精确控制

### 5.3 为什么镜头语言是必填？

这是一个**关键认知转变**带来的设计决策：

传统编剧场景中，镜头语言是选填的——人类演员和摄影师有主观能动性。
但在 AI 短剧管线中，下游的视频模型是"木头"。没有运镜指令 = 输出静态画面。

**Gemini 指出**：镜头语言不是"锦上添花"，而是"下游管线的硬通货"。

### 5.4 为什么嵌套控制在 3 层？

更深嵌套（如 PDF 参考的 7-8 层）适合学术化的镜头理论，但：
- 作者编辑时需要不断展开/折叠 → 体验差
- 下游解析出错概率指数增长
- 3 层已足够表达"场景 → 镜头 → 对白"的核心结构

---

## 6. 完整示例

```yaml
meta:
  title: "三体 · 红岸"
  source: "三体"
  author: "刘慈欣"
  genre: "科幻悬疑"
  total_scenes: 2
  total_shots: 6
  total_duration_estimate: "50s"
  target_platform: "抖音短剧"
  language: "zh-CN"
  version: "0.1.0"

characters:
  - character_id: "char_000"
    canonical_name: "叶文洁"
    aliases: ["小叶", "文洁", "叶老师"]
    description: "年轻的女天体物理学家，孤独而执着，背负着那个时代的创伤"
    role_type: "protagonist"
    gender: "female"
    age_range: "25-30"
  - character_id: "char_001"
    canonical_name: "雷志成"
    aliases: ["雷政委", "老雷"]
    description: "红岸基地政委，务实谨慎，对叶文洁怀有复杂的关注"
    role_type: "supporting"
    gender: "male"
    age_range: "45-50"

scenes:
  - scene_id: "s01"
    scene_number: 1
    location: "红岸基地 · 山顶 · 夜"
    time_of_day: "night"
    era: "1970年代"
    atmosphere: "压抑、孤独、星空浩瀚"
    weather: "寒风凛冽"
    duration_estimate: "25s"
    source_paragraphs: [0, 1, 2]
    shots:
      - shot_id: "s01_01"
        shot_number: 1
        shot_type: "大远景"
        camera_movement: "缓慢推进"
        focus_subject: "山顶的射电望远镜"
        visual_prompt: >-
          A massive radio telescope dish on a snowy mountain peak at night,
          slowly pushing in, starry sky with the Milky Way visible,
          cold blue tone, 1970s China military base aesthetic,
          cinematic wide shot
        duration: "5s"
        source_paragraphs: [0]
      - shot_id: "s01_02"
        shot_number: 2
        shot_type: "近景"
        camera_movement: "固定"
        focus_subject: "叶文洁"
        visual_prompt: >-
          Close-up of a young Chinese woman in 1970s military coat,
          looking up at the sky with a mix of wonder and sadness,
          cold winter wind blowing her hair, warm campfire light on her face,
          cinematic, deep emotional portrait
        duration: "8s"
        dialogue:
          character: "叶文洁"
          character_id: "char_000"
          line: "如果有人在听……请回答。"
          emotion: "孤独、试探"
        source_paragraphs: [1]
      - shot_id: "s01_03"
        shot_number: 3
        shot_type: "大远景"
        camera_movement: "拉远"
        focus_subject: "叶文洁与望远镜渐行渐远"
        visual_prompt: >-
          Wide shot pulling out from a tiny human figure standing next to
          a giant radio telescope on a snowy mountain peak, wind blowing snow,
          starry sky, lonely and vast, cinematic, cold blue color grade
        duration: "5s"
        sfx: "风声渐强"
        source_paragraphs: [2]
  - scene_id: "s02"
    scene_number: 2
    location: "红岸基地 · 控制室 · 夜"
    time_of_day: "interior"
    era: "1970年代"
    atmosphere: "温暖、紧张、压抑的封闭感"
    weather: ""
    duration_estimate: "25s"
    source_paragraphs: [3, 4]
    shots:
      - shot_id: "s02_01"
        shot_number: 1
        shot_type: "中景"
        camera_movement: "左摇"
        focus_subject: "控制室内景"
        visual_prompt: >-
          Interior of a 1970s Chinese military control room, rows of
          vintage electronic equipment, warm amber lighting from old lamps,
          pan left to reveal the room, analog dials and paper printouts,
          cinematic, nostalgic color grade
        duration: "5s"
        sfx: "仪器蜂鸣声，低沉的电流声"
        source_paragraphs: [3]
      - shot_id: "s02_02"
        shot_number: 2
        shot_type: "近景"
        camera_movement: "推进"
        focus_subject: "雷志成"
        visual_prompt: >-
          Medium close-up of a middle-aged Chinese man in military uniform
          sitting at a control console, holding a cup of hot tea,
          looking concerned, warm amber light, subtle push-in to increase tension,
          cinematic portrait
        duration: "6s"
        dialogue:
          character: "雷志成"
          character_id: "char_001"
          line: "确定不是苏联的干扰？"
          emotion: "怀疑、警惕"
        source_paragraphs: [4]
      - shot_id: "s02_03"
        shot_number: 3
        shot_type: "特写"
        camera_movement: "快速变焦"
        focus_subject: "示波器上的异常波形"
        visual_prompt: >-
          Extreme close-up of an analog oscilloscope screen, a strange
          stable waveform pattern appearing, quick crash zoom to emphasize
          the shock, green CRT glow, 1970s technology, dramatic tension
        duration: "3s"
        sfx: "电子蜂鸣声突然变得急促"
        source_paragraphs: [4]
```

---

## 7. 版本演进计划

| 版本 | 核心变更 | 状态 |
|------|----------|:--:|
| v0.1.0 | 核心三层结构 Meta → Scene → Shot | ✅ |
| v0.2.0 | SQLite 持久化、历史记录、内联编辑、可拖拽面板 | ✅ |
| v0.3.0 | tiktoken 精准计数、增量角色消歧、SSE 日志流、文件拖拽 | ✅ |
| v0.4.0 | C/S/P 素材编号、Timeline 时间轴、压缩包导出 | ✅ |
| v0.5.0 | 事件总线 + max_tokens=8192 + Chunk 重试 + SSE 心跳 | ✅ 当前 |
| v0.6.0 | 多集续写、跨文件资产复用、尾帧延长机制 | 🔜 规划中 |

---

## 8. v0.4 演进：从"文字剧本"到"多模态资产调度引擎"

v0.4 的核心认知升级：Looploop 的输出不只是"给 AI 导演看的"，更是"给一系列 AI 工具链消费的"——画图工具需要角色参考 prompt，视频工具需要时间轴分镜，人需要可读的素材编号。

### 8.1 C/S/P 素材编号体系

**为什么从 `char_000` 演进到 `C01`？**

`char_000` 是人机之间妥协的产物——机器需要唯一索引，但人类无法在大量角色中快速定位"第 0 号角色"。Seedance2 社区广泛使用 `@C01`、`@S01` 等符号引用素材，Looploop 需要与这一生态对齐。

**设计策略**：`character_id` 与 `material_id` 共存。

```yaml
characters:
  - character_id: "char_000"   # 机器内部索引，保证唯一性和消歧
    material_id: "C01"         # 人类可读编号，供下游工具 @C01 引用
    canonical_name: "叶文洁"
```

- `character_id` 保持 `char_NNN` 格式不变，确保所有 dialogue 引用的稳定性
- `material_id` 是新增的展示层字段，格式为 `C01`/`S01`
- 两者映射关系在 `scene_merger.build_screenplay()` 中自动生成

**material_manifest.yaml 的设计目的**：与分镜脚本物理分离。一份 20 集短剧有大量重复出现的角色和场景，将素材清单独立为 `manifest.yaml` 后：
- 下游 AI 画图工具可批量消费所有角色的 visual_prompt
- 多集之间可复用同一份 manifest，保持视觉一致性

### 8.2 Timeline 镜头内时间轴分段

**为什么需要 timeline？**

Seedance2 和可灵 2.0 的生成范式已经进化到秒级控制。一个 15s 的镜头，如果只有一个笼统的 `visual_prompt`，视频模型会随机分配画面。timeline 将 15s 拆为 3-4 个时间窗口，每个窗口有独立的画面描述：

```yaml
shots:
  - shot_id: "s01_01"
    duration: "15s"
    visual_prompt: "A snowy mountain base, cinematic..."
    timeline:
      - "0-3s: 高空俯拍，远景建立红岸基地的荒凉感"
      - "3-8s: 缓慢推进至山顶，射电望远镜逐渐清晰"
      - "8-12s: 近景捕捉叶文洁的微表情，风雪中凝视天空"
      - "12-15s: 拉远至大远景，孤独感收尾"
```

**设计策略**：`timeline` 是可选字段，保持向后兼容。

- LLM 优先从文本中推演时段划分
- LLM 未输出时自动合成单段 fallback：`"0-{duration}s: {focus_subject} - {shot_type} · {camera_movement}"`
- `model_dump()` 默认排除 `None` 值，不增加无 timeline 镜头的 JSON 体积

**与 visual_prompt 的关系**：

| 字段 | 回答的问题 | 受众 |
|------|-----------|------|
| `visual_prompt` | "拍什么？" — 画面内容、风格、色调 | T2V 模型 |
| `timeline` | "怎么拍？" — 镜头何时推进、何时特写 | 导演/剪辑 |

### 8.3 素材清单独立导出

传统做法是将所有信息塞进一个 YAML。v0.4 将素材清单（角色/场景的静态属性）与分镜脚本（镜头的动态时间线）物理分离：

```
导出 → All in One (.zip)
  ├── [标题]_剧本.yaml        # 完整剧本（含 timeline + dialogue）
  ├── [标题]_素材清单.yaml     # 仅 C/S/P 的静态描述，供画图工具消费
  └── [标题]_剧本.docx        # 人类可读版本
```

这份 manifest 可以在多集之间复用以保持角色一致性，这也是 v0.5 多集叙事引擎的基础设施。

---

> **Looploop v0.4 的本质**：一份结构化文档，同时被人类编辑、AI 画图、AI 视频三条管线并行消费。

---

## 9. v0.5.0 演进：异步长文本防爆架构

v0.5.0 的核心命题是解决 7.6 万字以上长文本的 Pipeline 崩溃问题。这不是 Schema 层面的设计——字段定义无需任何变更——而是**运行时架构**的升级。

### 9.1 从双调用到单次 Pipeline

v0.4 以前，Pipeline 为了同时获取"进度流"和"最终结果"，被拆分为两次执行：`run_with_progress()` 产 SSE 事件，`run()` 产 Screenplay。每次执行都触发完整的 LLM 调用链，Token 资费翻倍。

v0.5.0 将两者合并为单一的 `run_pipeline()` async generator：每个批次提取完成后立即 yield 进度事件，最终阶段 yield `stage="result"` + 完整 Screenplay。外部通过 `async for` 驱动，Token 消耗减半。

### 9.2 NOTIFICATION_BUS 事件总线

v0.4 的 SSE 端点内部是 `while True: await asyncio.sleep(0.3)` 的 SQLite 轮询循环。每当进度更新时读取数据库、序列化 JSON、推送给客户端。在高并发长文本场景下，SQLite 频繁发生锁竞争且 CPU 空转。

v0.5.0 引入 `NOTIFICATION_BUS: dict[str, asyncio.Queue]` 内存事件总线：Pipeline 生产进度事件 → `await queue.put(data)` 即时推送 → SSE 消费者 `await queue.get()` 被数据唤醒。SQLite 降级为仅持久化快照，SSE 零磁盘 I/O。

### 9.3 两阶段角色消歧 + 全局去重

v0.4 的增量消歧（`resolve_incremental`）每 3 个 Chunk 运行一次，但不同批次之间不做跨批次归并。v0.5.0 新增 `CharacterResolver.deduplicate()` 作为全局后处理：

- Phase 1：纯 Python 字典做同名合并（name_to_id 映射），零 LLM 开销
- Phase 2：LLM 语义消歧，识别"林教头=林震南=林总镖头"等跨名称同人
- 通过 `asyncio.to_thread()` 扔给线程池，防止阻塞事件循环

### 9.4 三层防爆体系

| 层级 | 机制 | 防护场景 |
|------|------|----------|
| 输出管道 | `max_tokens=8192` | LLM 单次输出物理上限翻倍 |
| 本地容错 | 逐 Chunk 独立重试 (2 retry) | 单块失败不拖垮同批其他块 |
| 尾部修复 | SafeParser `_try_auto_close()` | JSON 末尾缺失 `]}` 时 Python 规则补全 |

### 9.5 SSE 15s 心跳

Pipeline 等待 DeepSeek 响应时（单次 LLM 调用可达 80-120s），SSE 连接可能被客户端/代理判定为死连接。v0.5.0 在 SSE `event_generator` 中用 `asyncio.wait_for(queue.get(), timeout=15.0)` 包裹，超时则发送 `: ping\n\n`（SSE 注释行，浏览器不解析但维持 TCP 活跃）。配合客户端 `read=None` 不限读时，连接存活从 120s 提升至 386s+。
