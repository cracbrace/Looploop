"""
L2 集成：SceneMerger.build_screenplay 的 Meta 默认值。

迁移对照（backend/test_pipeline.py → 本文件）：
    test_build_screenplay_without_meta
        → test_build_screenplay_without_meta_overrides      ← Bug 2 回归
          test_build_screenplay_passes_pydantic_revalidation
          test_build_screenplay_applies_meta_overrides

本文件的核心价值：**docs/Testing_Lessons.md#Bug-2 的回归固化**。

Bug 2 原貌：`build_screenplay(meta_overrides=None)` 时 title/source/author/genre 取空字符串
`""`，撞上 `Meta.title` 的 `Field(min_length=1)`，抛
`Meta.title: String should have at least 1 character (input_value='')`。

它当时漏网的原因：旧测试直接构造了一个「完美 Screenplay」，`meta_overrides=None`
这条 else 分支从未被执行（docs/Testing_Lessons.md §4.4）。
"""

from __future__ import annotations

from backend.engine.scene_merger import SceneMerger
from backend.models import Screenplay


def test_build_screenplay_without_meta_overrides(sample_scenes, sample_registry):
    """
    回归 docs/Testing_Lessons.md#Bug-2。

    meta_overrides=None 是 UI 不填标题时的真实路径，默认值必须是非空字符串。
    若有人把默认值改回 ""，本用例会以 ValidationError 变红。
    """
    screenplay = SceneMerger().build_screenplay(sample_scenes, sample_registry)

    assert screenplay is not None
    assert screenplay.meta.title != "", "title 回落到空字符串 —— Bug 2 复发"
    assert screenplay.meta.title == "Untitled", f"got '{screenplay.meta.title}'"
    assert screenplay.meta.author == "Unknown", f"got '{screenplay.meta.author}'"
    assert screenplay.meta.genre == "General", f"got '{screenplay.meta.genre}'"
    assert screenplay.meta.total_scenes == 1, f"got {screenplay.meta.total_scenes}"
    assert screenplay.meta.total_shots == 1, f"got {screenplay.meta.total_shots}"


def test_build_screenplay_passes_pydantic_revalidation(sample_scenes, sample_registry):
    """产出的 Screenplay 再走一次 model_validate 必须无损——序列化前的最后一道闸。"""
    screenplay = SceneMerger().build_screenplay(sample_scenes, sample_registry)

    revalidated = Screenplay.model_validate(screenplay.model_dump())

    assert revalidated.model_dump() == screenplay.model_dump()


def test_build_screenplay_applies_meta_overrides(sample_scenes, sample_registry):
    """if meta_overrides 分支：显式传入的字段生效，未传的仍回落默认值。"""
    screenplay = SceneMerger().build_screenplay(
        sample_scenes, sample_registry, {"title": "三体", "genre": "科幻"}
    )

    assert screenplay.meta.title == "三体", f"got '{screenplay.meta.title}'"
    assert screenplay.meta.genre == "科幻", f"got '{screenplay.meta.genre}'"
    assert screenplay.meta.author == "Unknown", f"got '{screenplay.meta.author}'"


def test_build_screenplay_maps_registry_to_characters(sample_scenes, sample_registry):
    """registry 应被转成 Characters，并分配人类可读 material_id（C01 起）。"""
    screenplay = SceneMerger().build_screenplay(sample_scenes, sample_registry)

    assert [c.character_id for c in screenplay.characters] == ["char_000"]
    assert screenplay.characters[0].canonical_name == "叶文洁"
    assert screenplay.characters[0].material_id == "C01"
