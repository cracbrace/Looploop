"""
L2 集成：SceneMerger 的相邻合并、编号重排与时长计算。

迁移对照（backend/test_pipeline.py → 本文件）：
    test_scene_merger_adjacent
        → test_merge_combines_adjacent_same_location_scenes   （原 check("adjacent merged")
                                                                      "shots combined")
          test_merge_renumbers_scenes_and_shots               （原 check("scene id formatted")
                                                                      "shot ids formatted")
          test_build_screenplay_computes_total_duration       （原 check("duration calculated")）
          test_merge_keeps_different_locations_apart          （新增：_should_merge 的 False 分支）

为什么单独盯「编号重排」：merge() 先用 placeholder（s00 / s00_00）造对象、再统一重排。
这是最容易在重构中被静默改坏的步骤——编号错乱不会抛异常，只会毁掉下游素材对齐。
"""

from __future__ import annotations

from backend.engine.scene_merger import SceneMerger


def test_merge_combines_adjacent_same_location_scenes(adjacent_raw_scenes, adjacent_registry):
    """同地点同时间且原文相邻 → 合并为 1 个 Scene，两个镜头的顺序保持原样。"""
    scenes = SceneMerger().merge(adjacent_raw_scenes, adjacent_registry)

    assert len(scenes) == 1, f"got {len(scenes)} scenes"
    assert len(scenes[0].shots) == 2, f"got {len(scenes[0].shots)} shots"


def test_merge_renumbers_scenes_and_shots(adjacent_raw_scenes, adjacent_registry):
    """编号必须重排为 s01 / s01_01 / s01_02，不能残留 placeholder。"""
    scenes = SceneMerger().merge(adjacent_raw_scenes, adjacent_registry)

    assert scenes[0].scene_id == "s01", f"got '{scenes[0].scene_id}'"
    assert scenes[0].material_id == "S01", f"got '{scenes[0].material_id}'"
    assert [s.shot_id for s in scenes[0].shots] == ["s01_01", "s01_02"]
    assert [s.shot_number for s in scenes[0].shots] == [1, 2]


def test_build_screenplay_computes_total_duration(adjacent_raw_scenes, adjacent_registry):
    """8s + 6s = 14s——总时长由镜头时长累加得出（原 check("duration calculated")）。"""
    merger = SceneMerger()
    scenes = merger.merge(adjacent_raw_scenes, adjacent_registry)

    screenplay = merger.build_screenplay(scenes, adjacent_registry)

    assert screenplay.meta.total_duration_estimate == "14s", (
        f"got '{screenplay.meta.total_duration_estimate}'"
    )


def test_merge_keeps_different_locations_apart(raw_scene_factory, adjacent_registry):
    """地点不同 → 不合并。这个 False 分支旧脚本从未覆盖。"""
    raw_scenes = [
        raw_scene_factory(location="指挥室"),
        raw_scene_factory(location="走廊", source_paragraphs=(2, 3)),
    ]

    scenes = SceneMerger().merge(raw_scenes, adjacent_registry)

    assert len(scenes) == 2, f"got {len(scenes)} scenes"
    assert [s.scene_id for s in scenes] == ["s01", "s02"]
    assert scenes[0].location == "指挥室"
    assert scenes[1].location == "走廊"


def test_merge_empty_input_returns_empty_list():
    """空输入 → 空列表（merge 的早返回守卫）。"""
    assert SceneMerger().merge([], {}) == []
