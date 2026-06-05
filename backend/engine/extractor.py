"""
逐段提取模块

将文本 Chunk 送入 LLM，提取结构化信息：场景、镜头、对白、角色。
每个 Chunk 独立处理，但通过注入全局角色字典保持一致性。
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field

from backend.llm_client import LLMClient


# ============================================================
# 中间数据结构
# ============================================================

@dataclass
class RawShot:
    """提取的原始镜头（尚未合并、消歧）"""
    shot_type: str            # 景别
    camera_movement: str      # 运镜
    focus_subject: str        # 焦点
    visual_prompt: str        # 视频生成 prompt
    background: str = ""
    character: str = ""       # 对白角色名（原始，可能是别名）
    line: str = ""            # 台词
    emotion: str = ""         # 情绪
    delivery: str = ""        # 台词节奏
    sfx: str = ""             # 音效
    bgm: str = ""             # 配乐
    duration: str = "5s"      # 时长
    source_paragraphs: list[int] = field(default_factory=list)


@dataclass
class RawScene:
    """提取的原始场景"""
    location: str             # 地点
    time_of_day: str          # 时间
    atmosphere: str           # 氛围
    weather: str = ""         # 天气
    era: str = ""             # 年代
    duration_estimate: str = "30s"
    source_paragraphs: list[int] = field(default_factory=list)
    shots: list[RawShot] = field(default_factory=list)


@dataclass
class ExtractionResult:
    """单次提取的完整结果"""
    chunk_id: str
    chapter_index: int
    scenes: list[RawScene]
    characters_found: list[str]  # 本段发现的角色名（含别名）


# ============================================================
# 提取器
# ============================================================

class ChapterExtractor:
    """
    逐段提取器。

    对每个 Chunk 调用 LLM，提取其中的场景-镜头-对白结构。
    prompt 中注入全局角色字典，确保别名不被使用。
    """

    # 系统提示——定义 LLM 的角色和能力
    SYSTEM_PROMPT = """你是一位资深的影视导演和剧本分析师。

你的任务是将小说文本精确转化为结构化的分镜头剧本。
你需要像一个真正的导演那样思考：何时用特写捕捉角色的微表情？
何时用远景展现环境和孤独感？镜头应该如何运动？

## 核心规则

1. **场景划分**：每当地点或时间发生明显变化，创建一个新场景
2. **镜头拆分**：基于文学描写的"镜头感"——一个完整的动作/情感节拍 ≈ 一个镜头
3. **视觉 prompt**：每个镜头的 visual_prompt 是给 AI 视频生成模型的直接输入
   - 必须用英文（视频模型训练数据以英文为主）
   - 必须包含：主体 + 动作/状态 + 环境 + 光线/色调 + 风格
   - 长度 ≥ 20 字符
4. **镜头语言**：你必须从文学描写中推断出最合适的景别和运镜
   - 大段场景描写 → 远景/大远景
   - 人物对话 → 中景/近景
   - 情感爆发 → 特写/大特写
   - 紧张追逐 → 手持 + 跟随
5. **对白提取**：逐字引用原文对白，不要改写
6. **角色名**：如果提供了角色表，请使用 canonical_name；如果遇到新角色，使用原文中的名字并在 characters_found 中列出

## 镜头语言参考

### 景别（shot_type）
- 大远景：极端宽广，环境 > 人物，建立世界观
- 远景：人物全身 + 环境
- 中景：腰部以上，日常对话
- 近景：胸部以上，情感表达
- 特写：面部或物体局部，情绪高潮
- 大特写：极致细节（眼神、手指）
- 双人镜头：两个人物同框
- 过肩镜头：从背后拍摄，主观视角

### 运镜（camera_movement）
- 固定：静止，冷静观察
- 推进：缓慢接近，紧张升级
- 拉远：缓慢远离，孤独/离别
- 左摇/右摇：水平转动视线
- 上摇/下摇：仰视/俯视
- 跟随：跟踪主体移动
- 环绕：围绕主体旋转
- 手持：晃动，紧张纪实感
- 快速变焦：急速推拉，震惊反转

输出格式：严格 JSON，格式见用户提示。"""

    def __init__(self, llm: LLMClient):
        self.llm = llm

    # ============================================================
    # 公开接口
    # ============================================================

    async def extract(
        self,
        chunk_text: str,
        chunk_id: str = "",
        chapter_index: int = 0,
        character_registry: dict | None = None,
    ) -> ExtractionResult:
        """
        从一个文本 Chunk 中提取结构化场景/镜头/对白。

        Args:
            chunk_text: 文本段内容
            chunk_id: Chunk 标识
            chapter_index: 所属章节索引
            character_registry: 全局角色字典（可选，用于保持一致性）

        Returns:
            ExtractionResult 包含提取的场景列表和角色列表
        """
        prompt = self._build_extraction_prompt(
            chunk_text, character_registry
        )

        raw_json = await self.llm.generate_json(
            prompt=prompt,
            system_prompt=self.SYSTEM_PROMPT,
            temperature=0.3,
        )

        return self._parse_response(
            raw_json, chunk_id, chapter_index
        )

    # ============================================================
    # 内部方法
    # ============================================================

    def _build_extraction_prompt(
        self,
        text: str,
        character_registry: dict | None = None,
    ) -> str:
        """构建提取 prompt"""

        registry_block = ""
        if character_registry:
            registry_entries = []
            for cid, char in character_registry.items():
                if isinstance(char, dict):
                    name = char.get("canonical_name", cid)
                    aliases = char.get("aliases", [])
                    desc = char.get("description", "")
                else:
                    name = char.canonical_name
                    aliases = char.aliases
                    desc = char.description
                aliases_str = "、".join(aliases) if aliases else "无"
                registry_entries.append(
                    f"  - {name}（别名：{aliases_str}）：{desc}"
                )
            if registry_entries:
                registry_block = (
                    "## 已知角色表（请使用 canonical_name，不要使用别名）\n"
                    + "\n".join(registry_entries)
                    + "\n\n"
                )

        prompt = f"""{registry_block}## 待处理文本

{text}

## 输出格式

请输出以下格式的 JSON 对象：

```json
{{
  "scenes": [
    {{
      "location": "地点名称（可加场景描述，如'红岸基地 · 山顶 · 夜'）",
      "time_of_day": "day|night|dawn|dusk|interior",
      "atmosphere": "情绪氛围，如'压抑、孤独'或'紧张、危险'",
      "weather": "天气（如无则空字符串）",
      "era": "年代背景（如可从上下文推断，否则空字符串）",
      "duration_estimate": "预估时长，如'30s'",
      "source_paragraphs": [段落索引],
      "shots": [
        {{
          "shot_type": "景别（从枚举中选择）",
          "camera_movement": "运镜（从枚举中选择）",
          "focus_subject": "镜头焦点（主体）",
          "visual_prompt": "英文视频生成 prompt（≥20 字符）",
          "background": "背景补充（无则空字符串）",
          "character": "对白角色名（无对白则空字符串）",
          "line": "台词原文（无则空字符串）",
          "emotion": "情绪（无对白则空字符串）",
          "delivery": "台词节奏：快|慢|停顿|打断|渐弱（无则空字符串）",
          "sfx": "音效（无则空字符串）",
          "bgm": "配乐方向（无则空字符串）",
          "duration": "镜头时长，如'8s'",
          "source_paragraphs": [原文段落索引]
        }}
      ]
    }}
  ],
  "characters_found": ["本段中新出现的角色名（不含已知角色表中已有的）"]
}}
```

请确保只输出合法 JSON，不要包含任何额外说明。"""
        return prompt

    def _parse_response(
        self,
        raw_json: str,
        chunk_id: str,
        chapter_index: int,
    ) -> ExtractionResult:
        """解析 LLM 返回的 JSON 为 ExtractionResult"""
        data = json.loads(raw_json)

        scenes = []
        for scene_data in data.get("scenes", []):
            shots = []
            for shot_data in scene_data.get("shots", []):
                shots.append(RawShot(
                    shot_type=shot_data.get("shot_type", ""),
                    camera_movement=shot_data.get("camera_movement", ""),
                    focus_subject=shot_data.get("focus_subject", ""),
                    visual_prompt=shot_data.get("visual_prompt", ""),
                    background=shot_data.get("background", ""),
                    character=shot_data.get("character", ""),
                    line=shot_data.get("line", ""),
                    emotion=shot_data.get("emotion", ""),
                    delivery=shot_data.get("delivery", ""),
                    sfx=shot_data.get("sfx", ""),
                    bgm=shot_data.get("bgm", ""),
                    duration=shot_data.get("duration", "5s"),
                    source_paragraphs=scene_data.get("source_paragraphs", []),
                ))

            scenes.append(RawScene(
                location=scene_data.get("location", ""),
                time_of_day=scene_data.get("time_of_day", ""),
                atmosphere=scene_data.get("atmosphere", ""),
                weather=scene_data.get("weather", ""),
                era=scene_data.get("era", ""),
                duration_estimate=scene_data.get("duration_estimate", "30s"),
                source_paragraphs=scene_data.get("source_paragraphs", []),
                shots=shots,
            ))

        return ExtractionResult(
            chunk_id=chunk_id,
            chapter_index=chapter_index,
            scenes=scenes,
            characters_found=data.get("characters_found", []),
        )
