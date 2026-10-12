"""
L2 集成层的共享构造数据。

分层原则（docs/Testing_Lessons.md §4.3）：模块间接口要用**真实类型**测试。
因此这里的 registry 全部由真实的 `ResolvedCharacter` dataclass 构造，
而不是 dict 替身——Bug 1 正是「用 dict 替身测出了假绿」的产物。
"""

from __future__ import annotations

import pytest

from backend.engine.character_resolver import ResolvedCharacter
from backend.engine.extractor import RawScene, RawShot
from backend.models import Dialogue, Scene, Shot

# 与旧脚本一致的视觉 prompt（≥20 字符）
VISUAL_PROMPT_A = (
    "A man in uniform at control panel, tense, 1970s China military base"
)
VISUAL_PROMPT_B = (
    "Close-up of engineer looking at radar, concerned expression, 1970s"
)


# ============================================================
# 角色字典
# ============================================================

@pytest.fixture
def registry() -> dict[str, ResolvedCharacter]:
    """叶文洁 + 雷志成的真实 registry（extractor 联合调用用）。"""
    return {
        "char_000": ResolvedCharacter(
            canonical_name="叶文洁",
            aliases=["小叶", "叶老师"],
            description="年轻女物理学家",
            role_type="protagonist",
            gender="female",
            age_range="25-30",
        ),
        "char_001": ResolvedCharacter(
            canonical_name="雷志成",
            aliases=["雷政委", "老雷"],
            description="基地政委",
            role_type="supporting",
            gender="male",
            age_range="45-50",
        ),
    }


@pytest.fixture
def sample_registry() -> dict[str, ResolvedCharacter]:
    """单角色 registry（build_screenplay 默认值分支用）。"""
    return {
        "char_000": ResolvedCharacter(
            canonical_name="叶文洁",
            aliases=["小叶"],
            description="测试",
            role_type="protagonist",
            gender="female",
            age_range="25-30",
        )
    }


@pytest.fixture
def adjacent_registry() -> dict[str, ResolvedCharacter]:
    """相邻合并场景用到的两个角色。"""
    return {
        "char_000": ResolvedCharacter(
            canonical_name="王建国",
            aliases=[],
            description="队长",
            role_type="supporting",
            gender="male",
            age_range="40-50",
        ),
        "char_001": ResolvedCharacter(
            canonical_name="李工程师",
            aliases=["老李"],
            description="工程师",
            role_type="supporting",
            gender="male",
            age_range="30-40",
        ),
    }


# ============================================================
# Scene（build_screenplay 输入）
# ============================================================

@pytest.fixture
def sample_scenes() -> list[Scene]:
    """单场景单镜头——旧脚本 test_build_screenplay_without_meta 的构造原样保留。"""
    return [
        Scene(
            scene_id="s01",
            scene_number=1,
            location="测试地点",
            time_of_day="night",
            atmosphere="孤独",
            duration_estimate="8s",
            shots=[
                Shot(
                    shot_id="s01_01",
                    shot_number=1,
                    shot_type="特写",
                    camera_movement="固定",
                    focus_subject="叶文洁",
                    visual_prompt=(
                        "A test visual prompt that is long enough for video generation"
                    ),
                    duration="8s",
                )
            ],
        )
    ]


# ============================================================
# RawScene 工厂（scene_merger 输入）
# ============================================================

@pytest.fixture
def raw_scene_factory():
    """
    构造 RawScene 的工厂。

    默认产出一段「指挥室 · interior · 王建国」的镜头，可通过参数改地点/时间/角色，
    因此同一个工厂既能造「该合并」的一对，也能造「不该合并」的一对。
    """

    def _make(
        location: str = "指挥室",
        time_of_day: str = "interior",
        atmosphere: str = "紧张",
        duration_estimate: str = "20s",
        source_paragraphs: tuple[int, ...] = (0, 1),
        shot_type: str = "中景",
        camera_movement: str = "固定",
        focus_subject: str = "王建国",
        visual_prompt: str = VISUAL_PROMPT_A,
        character: str = "王建国",
        line: str = "有异常。",
        duration: str = "8s",
    ) -> RawScene:
        return RawScene(
            location=location,
            time_of_day=time_of_day,
            atmosphere=atmosphere,
            duration_estimate=duration_estimate,
            source_paragraphs=list(source_paragraphs),
            shots=[
                RawShot(
                    shot_type=shot_type,
                    camera_movement=camera_movement,
                    focus_subject=focus_subject,
                    visual_prompt=visual_prompt,
                    character=character,
                    line=line,
                    emotion="紧张",
                    duration=duration,
                )
            ],
        )

    return _make


@pytest.fixture
def adjacent_raw_scenes(raw_scene_factory) -> list[RawScene]:
    """同地点同时间、且在原文中相邻的两个 RawScene——应当被合并成 1 个 Scene。"""
    return [
        raw_scene_factory(),
        raw_scene_factory(
            atmosphere="压抑",
            duration_estimate="15s",
            source_paragraphs=(2, 3),
            shot_type="近景",
            focus_subject="李工程师",
            visual_prompt=VISUAL_PROMPT_B,
            character="老李",
            line="我去查。",
            duration="6s",
        ),
    ]
