"""
L1 单元测试：Screenplay → YAML → Screenplay 往返一致性。

迁移对照（backend/test_pipeline.py → 本文件）：
    test_yaml_roundtrip → test_yaml_output_is_substantial   （原 check("yaml not empty")）
                          test_yaml_is_parseable             （原 check("yaml valid")）
                          test_yaml_preserves_fields         （原 check("meta preserved")
                                                                       "shots array exists"
                                                                       "shot_type preserved"）
                          test_yaml_roundtrip_is_lossless    （本 PR 加固：不止字段抽查，
                                                              整份 model_dump 逐字段比对）

为什么重要：YAML 是剧本交付给下游（导出 / 素材清单 / 人工审阅）的载体，
序列化丢字段会静默损坏交付物——状态码 200 骗不了这种 bug，只有往返比对能。
"""

from __future__ import annotations

import yaml
import pytest

from backend.models import Character, Meta, Scene, Screenplay, Shot
from backend.safe_parser import SafeParser


@pytest.fixture
def screenplay() -> Screenplay:
    """最小合法剧本：1 角色 / 1 场景 / 1 镜头，与旧脚本构造完全一致。"""
    return Screenplay(
        meta=Meta(
            title="测试",
            source="测试",
            author="测试",
            genre="科幻",
            total_scenes=1,
            total_shots=1,
            total_duration_estimate="8s",
        ),
        characters=[
            Character(
                character_id="char_000",
                canonical_name="叶文洁",
                aliases=["小叶"],
                description="测试",
                role_type="protagonist",
                gender="female",
                age_range="25-30",
            )
        ],
        scenes=[
            Scene(
                scene_id="s01",
                scene_number=1,
                location="基地",
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
                            "A close-up of a young woman looking up at the starry sky, "
                            "cinematic, 1970s"
                        ),
                        duration="8s",
                    )
                ],
            )
        ],
    )


def test_yaml_output_is_substantial(screenplay):
    """原 check("yaml not empty")：输出不是被截断/空的骨架。"""
    yaml_str = SafeParser.screenplay_to_yaml(screenplay)

    assert len(yaml_str) > 100, f"yaml length: {len(yaml_str)}"


def test_yaml_is_parseable(screenplay):
    """原 check("yaml valid")：产物必须是合法 YAML，下游解析器才吃得下。"""
    yaml_str = SafeParser.screenplay_to_yaml(screenplay)

    parsed = yaml.safe_load(yaml_str)

    assert parsed is not None


def test_yaml_preserves_fields(screenplay):
    """原 3 个字段抽查：meta / shots 数组 / shot_type 均已迁移。"""
    parsed = yaml.safe_load(SafeParser.screenplay_to_yaml(screenplay))

    assert parsed["meta"]["title"] == "测试", f"got {parsed['meta']['title']}"
    assert len(parsed["scenes"][0]["shots"]) == 1, f"got {parsed['scenes'][0]['shots']}"
    assert parsed["scenes"][0]["shots"][0]["shot_type"] == "特写"


def test_yaml_roundtrip_is_lossless(screenplay):
    """
    Screenplay → yaml → Screenplay 往返后逐字段一致。

    比字段抽查更强：新增/改名任何字段若序列化丢失，这里都会立刻变红。
    """
    yaml_str = SafeParser.screenplay_to_yaml(screenplay)

    restored = Screenplay.model_validate(yaml.safe_load(yaml_str))

    assert restored.model_dump() == screenplay.model_dump()
