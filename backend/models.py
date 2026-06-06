"""
Looploop 数据模型

YAML Schema 的 Pydantic 强类型定义。
贯穿整个系统：API 层用其校验请求/响应、引擎层用其校验 LLM 输出、
前端 TypeScript 类型也基于此生成。
"""

from __future__ import annotations

from typing import Literal, Optional

from pydantic import BaseModel, Field, field_validator


# ============================================================
# 枚举类型
# ============================================================

ShotType = Literal[
    "大远景",   # Extreme Wide  — 环境主导，人物极小
    "远景",     # Wide         — 人物全身 + 环境
    "中景",     # Medium       — 人物腰部以上
    "近景",     # Close-Up     — 人物胸部以上
    "特写",     # Extreme CU   — 面部或物体细节
    "大特写",   # Macro        — 极致细节
    "双人镜头",  # Two-Shot     — 两个角色同框
    "过肩镜头",  # OTS          — 从背后拍对方
]

CameraMovement = Literal[
    "固定",     # Static       — 静止不动，冷静观察
    "推进",     # Push In      — 缓慢接近，紧张升级
    "拉远",     # Pull Out     — 缓慢远离，孤独/离别
    "左摇",     # Pan Left     — 水平左转
    "右摇",     # Pan Right    — 水平右转
    "上摇",     # Tilt Up      — 仰视，崇高感
    "下摇",     # Tilt Down    — 俯视，渺小感
    "跟随",     # Tracking     — 跟踪主体移动
    "环绕",     # Arc          — 环绕主体，戏剧性
    "手持",     # Handheld     — 晃动，紧张/纪实
    "快速变焦",  # Crash Zoom   — 急速推拉，震惊/反转
]

TimeOfDay = Literal["day", "night", "dawn", "dusk", "interior"]

RoleType = Literal["protagonist", "antagonist", "supporting", "cameo"]

Gender = Literal["male", "female", "other"]


# ============================================================
# 对白
# ============================================================

class Dialogue(BaseModel):
    """镜头中的对白/台词"""

    character: str = Field(
        ...,
        description="说话角色的 canonical_name，如'叶文洁'",
        min_length=1,
    )
    character_id: str = Field(
        ...,
        description="对应 Character.character_id，如'char_001'",
        pattern=r"^char_\d{3}$",
    )
    line: str = Field(
        ...,
        description="台词原文",
        min_length=1,
    )
    emotion: str = Field(
        ...,
        description="语气情绪，如'冷漠'、'激动'、'试探'、'悲伤'",
    )
    delivery: Optional[str] = Field(
        default=None,
        description="台词节奏：'快'|'慢'|'停顿'|'打断'|'渐弱'",
    )


# ============================================================
# 镜头（最小原子）
# ============================================================

class Shot(BaseModel):
    """
    单个镜头——下游视频生成模型的直接指令。

    设计原则（来自 Gemini 的核心洞察）：
    shot_type 和 camera_movement 是必填字段。
    因为下游的 Runway/可灵是"木头"，没有主观能动性——
    如果剧本里只有台词和动作描述，生成的视频会极度死板。
    """

    shot_id: str = Field(
        ...,
        description="全局唯一镜头 ID，如's01_01'",
        pattern=r"^s\d{2}_\d{2}$",
        examples=["s01_01", "s02_03"],
    )
    shot_number: int = Field(
        ...,
        description="场景内镜头序号，从 1 开始",
        ge=1,
    )

    # === 镜头语言（必填——下游视频模型的硬指令） ===
    shot_type: ShotType = Field(
        ...,
        description="景别：'大远景'|'远景'|'中景'|'近景'|'特写'|'大特写'|'双人镜头'|'过肩镜头'",
    )
    camera_movement: CameraMovement = Field(
        ...,
        description="运镜：'固定'|'推进'|'拉远'|'左摇'|'右摇'|'上摇'|'下摇'|'跟随'|'环绕'|'手持'|'快速变焦'",
    )

    # === 画面内容 ===
    focus_subject: str = Field(
        ...,
        description="镜头焦点——画面中最重要的视觉主体，如'叶文洁'、'射电望远镜'、'信号灯'",
        min_length=1,
    )
    visual_prompt: str = Field(
        ...,
        description=(
            "直接喂给视频生成模型（Runway/可灵）的英文 prompt。"
            "需包含：主体描述 + 动作/表情 + 环境氛围 + 色调/光线 + 年代/风格。"
            "≥20 字符以保证信息量足够。"
        ),
        min_length=20,
    )
    background: Optional[str] = Field(
        default=None,
        description="背景环境补充描述，可选",
    )

    # === 音频 ===
    dialogue: Optional[Dialogue] = Field(
        default=None,
        description="该镜头中的对白，如无对白则为 null",
    )
    sfx: Optional[str] = Field(
        default=None,
        description="音效描述，如'电子蜂鸣声，从无到有'",
    )
    bgm: Optional[str] = Field(
        default=None,
        description="配乐方向，如'低沉弦乐，渐强'",
    )

    # === 时间 ===
    duration: str = Field(
        ...,
        description="本镜头预估时长，如'5s'、'8s'、'3s'",
        pattern=r"^\d+s$",
        examples=["5s", "8s"],
    )
    # 🆕 v0.4: 镜头内时间轴分段描述
    timeline: Optional[list[str]] = Field(
        default=None,
        description="镜头内部分段时间描述，如['0-3s: 高空俯拍，场景建立', '3-6s: 镜头推进']",
        examples=[["0-3s: 远景建立场景", "3-8s: 推进至近景"]],
    )

    # === 溯源 ===
    source_paragraphs: list[int] = Field(
        default_factory=list,
        description="对应原文段落索引（0-based），用于前端联动高亮",
    )

    # === 扩展 ===
    extra: dict = Field(
        default_factory=dict,
        description="未来扩展字段（如灯光、服装、特效标记等）",
    )

    @field_validator("visual_prompt")
    @classmethod
    def visual_prompt_min_length(cls, v: str) -> str:
        """确保 visual_prompt 长度足以用于视频生成"""
        if len(v.strip()) < 20:
            raise ValueError(
                f"visual_prompt 太短（{len(v)} 字符），"
                f"无法用于视频生成模型。请扩展至 ≥20 字符。"
            )
        return v

    @field_validator("shot_type")
    @classmethod
    def validate_shot_type(cls, v: str) -> str:
        valid = (
            "大远景", "远景", "中景", "近景", "特写", "大特写",
            "双人镜头", "过肩镜头",
        )
        if v not in valid:
            raise ValueError(f"非法的 shot_type: '{v}'。合法值：{valid}")
        return v

    @field_validator("camera_movement")
    @classmethod
    def validate_camera_movement(cls, v: str) -> str:
        valid = (
            "固定", "推进", "拉远", "左摇", "右摇", "上摇", "下摇",
            "跟随", "环绕", "手持", "快速变焦",
        )
        if v not in valid:
            raise ValueError(f"非法的 camera_movement: '{v}'。合法值：{valid}")
        return v


# ============================================================
# 场景
# ============================================================

class Scene(BaseModel):
    """一个连续时空中的场景，包含多个镜头"""

    scene_id: str = Field(
        ...,
        description="机器内部唯一场景 ID，如's01'",
        pattern=r"^s\d{2}$",
        examples=["s01", "s02"],
    )
    material_id: str = Field(
        default="",
        description="人类可读素材编号，如'S01'",
        examples=["S01", "S02"],
    )
    scene_number: int = Field(
        ...,
        description="场景序号，从 1 开始",
        ge=1,
    )

    # --- 时空定位 ---
    location: str = Field(
        ...,
        description="地点，如'红岸基地 · 山顶 · 夜'",
        min_length=1,
    )
    time_of_day: TimeOfDay = Field(
        ...,
        description="时间：'day'|'night'|'dawn'|'dusk'|'interior'",
    )
    era: Optional[str] = Field(
        default=None,
        description="时代背景，如'1970年代'、'近未来'、'民国'",
    )

    # --- 氛围 ---
    atmosphere: str = Field(
        ...,
        description="情绪氛围，如'压抑、孤独、危险'、'温暖、怀旧'",
    )
    weather: Optional[str] = Field(
        default=None,
        description="天气，如'暴风雪'、'阴雨'、'晴空'",
    )

    # --- 元数据 ---
    duration_estimate: str = Field(
        ...,
        description="预估本场景总时长，如'45s'",
        pattern=r"^\d+s$",
    )
    source_paragraphs: list[int] = Field(
        default_factory=list,
        description="对应原文段落索引（0-based）",
    )

    # --- 镜头列表 ---
    shots: list[Shot] = Field(
        ...,
        description="场景内的全部镜头",
        min_length=1,
    )

    @field_validator("shots")
    @classmethod
    def at_least_one_shot(cls, v: list[Shot]) -> list[Shot]:
        if len(v) == 0:
            raise ValueError("每个场景至少需要 1 个镜头")
        return v


# ============================================================
# 角色
# ============================================================

class Character(BaseModel):
    """
    全局角色字典中的角色条目。

    角色消歧模块（CharacterResolver）的核心数据输出：
    将所有别名收拢到唯一的 canonical_name。
    """

    character_id: str = Field(
        ...,
        description="机器内部唯一 ID，如'char_001'",
        pattern=r"^char_\d{3}$",
    )
    material_id: str = Field(
        default="",
        description="人类可读素材编号，如'C01'。供下游画图/视频工具引用",
        examples=["C01", "C02"],
    )
    canonical_name: str = Field(
        ...,
        description="规范名称，如'叶文洁'。所有对话中必须使用此名称。",
        min_length=1,
    )
    aliases: list[str] = Field(
        default_factory=list,
        description="所有别名，如['叶老师','小叶','文洁']",
    )
    description: str = Field(
        ...,
        description="一句话角色描述，如'年轻的女天体物理学家，孤独而执着'",
    )
    role_type: RoleType = Field(
        default="supporting",
        description="角色类型：'protagonist'|'antagonist'|'supporting'|'cameo'",
    )
    gender: Gender = Field(
        default="other",
        description="性别：'male'|'female'|'other'",
    )
    age_range: str = Field(
        default="unknown",
        description="年龄范围，如'25-30'、'50+'、'unknown'",
    )


# ============================================================
# 元信息
# ============================================================

class Meta(BaseModel):
    """剧本全局元信息"""

    title: str = Field(
        ...,
        description="剧本名称",
        min_length=1,
    )
    source: str = Field(
        ...,
        description="原著名称",
    )
    author: str = Field(
        ...,
        description="原作者",
    )
    genre: str = Field(
        ...,
        description="类型标签，如'科幻悬疑'、'都市爱情'、'古装权谋'",
    )
    total_scenes: int = Field(
        ...,
        description="场景总数",
        ge=1,
    )
    total_shots: int = Field(
        ...,
        description="镜头总数",
        ge=1,
    )
    total_duration_estimate: str = Field(
        ...,
        description="预估总时长，如'3min20s'",
    )
    target_platform: Optional[str] = Field(
        default=None,
        description="目标平台，如'抖音短剧'、'Reelshort'、'YouTube Shorts'",
    )
    language: str = Field(
        default="zh-CN",
        description="语言代码",
    )
    version: str = Field(
        default="0.1.0",
        description="Looploop Schema 版本号",
    )


# ============================================================
# 完整剧本
# ============================================================

class Screenplay(BaseModel):
    """
    最终输出的完整剧本。

    这是整个 Looploop 系统的核心数据产品——
    上一份是小说原文，下一站是视频生成模型。
    """

    meta: Meta = Field(..., description="剧本元信息")
    characters: list[Character] = Field(
        default_factory=list,
        description="全局角色字典——角色消歧的核心数据源",
    )
    scenes: list[Scene] = Field(
        ...,
        description="场景列表",
        min_length=1,
    )

    @field_validator("scenes")
    @classmethod
    def at_least_one_scene(cls, v: list[Scene]) -> list[Scene]:
        if len(v) == 0:
            raise ValueError("剧本至少需要 1 个场景")
        return v
