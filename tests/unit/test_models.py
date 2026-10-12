"""
L1 单元测试：Pydantic 数据模型的约束与边界。

迁移对照（backend/test_pipeline.py → 本文件）：
    test_shot_validation_valid     → test_valid_shot_is_accepted
    test_shot_validation_invalid   → test_invalid_shot_is_rejected[visual-prompt-too-short
                                                               |bad-shot-type
                                                               |bad-camera-movement
                                                               |bad-shot-id]
    test_scene_validation          → test_scene_rejects_empty_shots
    test_character_model           → test_character_stores_fields

改写要点：
  - check(name, try/except ValidationError) → pytest.raises(ValidationError, match=...)
  - match 锚定出错字段名（Pydantic 的 ValidationError 文本包含 loc 路径），
    比锚定具体英文/中文报错文案更耐版本升级
  - 相对旧脚本新增 1 例 camera_movement 非法枚举：它有独立 field_validator，
    旧脚本漏测（见 PR 描述「相对旧脚本的增量」）
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from backend.models import Character, Scene, Shot

# 旧脚本中反复出现的合法 prompt（≥20 字符，满足 min_length 与 field_validator 双重约束）
VALID_VISUAL_PROMPT = (
    "Close-up of a young woman in military coat, looking at stars, cinematic, 1970s China snow"
)


def make_shot(**overrides) -> dict:
    """构造一份合法 Shot 的字段字典，按需覆盖单个字段来制造非法输入。"""
    data = {
        "shot_id": "s01_01",
        "shot_number": 1,
        "shot_type": "特写",
        "camera_movement": "推进",
        "focus_subject": "叶文洁",
        "visual_prompt": VALID_VISUAL_PROMPT,
        "duration": "8s",
    }
    data.update(overrides)
    return data


# ============================================================
# Shot
# ============================================================

def test_valid_shot_is_accepted():
    """原 check("valid shot created")：合法字段能构造出 Shot。"""
    shot = Shot(**make_shot())

    assert shot.shot_type == "特写", f"got {shot.shot_type}"


@pytest.mark.parametrize(
    "overrides, expected_field, case",
    [
        ({"visual_prompt": "short"}, "visual_prompt", "visual_prompt 过短"),
        ({"shot_type": "bad_type"}, "shot_type", "shot_type 非法枚举"),
        ({"camera_movement": "bad_move"}, "camera_movement", "camera_movement 非法枚举"),
        ({"shot_id": "bad"}, "shot_id", "shot_id 格式错误"),
    ],
    ids=[
        "visual-prompt-too-short",
        "bad-shot-type",
        "bad-camera-movement",
        "bad-shot-id",
    ],
)
def test_invalid_shot_is_rejected(overrides, expected_field, case):
    """
    原 3 个 check("rejects ...")：非法 Shot 必须被 Pydantic 拦下。

    这些约束是下游视频生成模型的硬保证——放过去就会生成废片。
    """
    with pytest.raises(ValidationError, match=expected_field):
        Shot(**make_shot(**overrides))


# ============================================================
# Scene
# ============================================================

def test_scene_rejects_empty_shots():
    """原 check("rejects empty shots")：空镜头列表的场景没有意义，必须拒绝。"""
    with pytest.raises(ValidationError, match="shots"):
        Scene(
            scene_id="s01",
            scene_number=1,
            location="test",
            time_of_day="night",
            atmosphere="test",
            duration_estimate="10s",
            shots=[],
        )


# ============================================================
# Character
# ============================================================

def test_character_stores_fields():
    """原 check("valid character") + check("aliases stored")：角色与别名正确落库。"""
    character = Character(
        character_id="char_000",
        canonical_name="叶文洁",
        aliases=["小叶", "叶老师"],
        description="物理学家",
        role_type="protagonist",
        gender="female",
        age_range="25-30",
    )

    assert character.canonical_name == "叶文洁", f"got {character.canonical_name}"
    assert "小叶" in character.aliases, f"aliases: {character.aliases}"
