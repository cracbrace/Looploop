"""
L3 端到端：真实 LLM 驱动的完整 Pipeline。

迁移自 backend/test_pipeline.py::test_pipeline_e2e_real_llm（原 24 处 check()）。

分级机制（本 PR 的核心增量）：
    @pytest.mark.llm        → 让 `pytest -m "not llm"` 能整层排除，作为离线全量命令
    @pytest.mark.skipif     → 让不带 -m 的裸 `pytest` 在无 key 环境下 SKIP 而不是 FAIL
两者缺一不可：只有 marker 则裸 pytest 会红，只有 skipif 则无法按层排除且退出码语义模糊。
CI 依赖「无 key 时退出码为 0」这一性质。

跳过条件用 `settings.llm_api_key` 而不是 `os.getenv("LLM_API_KEY")`：
config.py 由 pydantic-settings 读取，.env 文件与环境变量都是它的输入源；
只查环境变量会在「有 .env、没导出环境变量」的常见本地配置下误判为无 key。

成本控制：真实 LLM 调用慢且付费，因此整个模块**只跑一次** Pipeline，
多个断言函数共享同一份 Screenplay（见 real_screenplay fixture）。
"""

from __future__ import annotations

import asyncio
from typing import get_args

import pytest

from backend.config import settings
from backend.engine.pipeline import Pipeline
from backend.llm_client import LLMClient
from backend.models import CameraMovement, Screenplay, ShotType
from backend.safe_parser import SafeParser

# 直接取自 Pydantic 模型定义，避免与 models.py 的枚举硬编码重复
VALID_SHOT_TYPES = set(get_args(ShotType))
VALID_CAMERA_MOVEMENTS = set(get_args(CameraMovement))

pytestmark = [
    pytest.mark.llm,
    pytest.mark.skipif(
        not settings.llm_api_key,
        reason="未配置 LLM API key（.env 的 LLM_API_KEY 或同名环境变量）",
    ),
]


async def _run_real_pipeline(text: str) -> Screenplay:
    """驱动真实 Pipeline，返回最终 Screenplay。"""
    pipeline = Pipeline(LLMClient())
    screenplay = None
    async for stage in pipeline.run_pipeline(text):
        if stage.stage == "result":
            screenplay = stage.data["screenplay"]
    return screenplay


# 模块级缓存：一次真实调用，多个断言函数复用
_OUTCOME: dict[str, object] = {}


@pytest.fixture
def real_screenplay(sample_text) -> Screenplay:
    """
    真实跑一次全链路，结果在本模块内共享。

    成功与失败都会被缓存：若 Pipeline 抛错，缓存异常再逐个断言函数重抛，
    否则每个断言函数都会重新付费跑一次，一次失败会放大成几分钟的账单。
    """
    if "outcome" not in _OUTCOME:
        try:
            _OUTCOME["outcome"] = ("ok", asyncio.run(_run_real_pipeline(sample_text)))
        except Exception as exc:  # noqa: BLE001 — 故意捕获并缓存，稍后原样重抛
            _OUTCOME["outcome"] = ("error", exc)

    kind, payload = _OUTCOME["outcome"]  # type: ignore[misc]
    if kind == "error":
        raise payload
    return payload  # type: ignore[return-value]


# ============================================================
# 结构完整性
# ============================================================

def test_screenplay_is_produced(real_screenplay):
    """原 check("screenplay not none"/"has meta"/"title not empty")。"""
    assert real_screenplay is not None
    assert real_screenplay.meta is not None
    assert real_screenplay.meta.title != "", "title 为空 —— Bug 2 类型的默认值问题"


def test_has_scenes_and_characters(real_screenplay):
    """原 check("has scenes")/check("has characters")。"""
    assert len(real_screenplay.scenes) >= 1, f"got {len(real_screenplay.scenes)} scenes"
    assert len(real_screenplay.characters) >= 1, (
        f"got {len(real_screenplay.characters)} characters"
    )


def test_meta_counts_match_actual(real_screenplay):
    """原 check("total_scenes matches")/check("total_shots matches")。"""
    actual_shots = sum(len(s.shots) for s in real_screenplay.scenes)

    assert real_screenplay.meta.total_scenes == len(real_screenplay.scenes)
    assert real_screenplay.meta.total_shots == actual_shots, (
        f"meta={real_screenplay.meta.total_shots}, actual={actual_shots}"
    )


# ============================================================
# 逐场景 / 逐镜头（旧脚本每项一个 check，这里汇总所有违规项）
# ============================================================

def test_scenes_have_required_fields(real_screenplay):
    """原「每个 scene」三条 check——汇总报告所有不合法场景，而不是只报第一个。"""
    bad = [
        s.scene_id
        for s in real_screenplay.scenes
        if not s.shots or not s.location or not s.atmosphere
    ]

    assert not bad, f"字段缺失的场景: {bad}"


def test_shots_use_valid_camera_language(real_screenplay):
    """
    原 check("valid type")/check("valid movement")。

    注：`Shot` 已用 Literal + field_validator 把这两项锁死，因此本断言对
    合法构造出来的 Screenplay 恒真。它守的不是「当前会不会错」，
    而是「schema 被无意放宽时会不会被察觉」——是契约文档，不是新鲜 bug 探测器。
    """
    bad_types = []
    bad_movements = []
    for scene in real_screenplay.scenes:
        for shot in scene.shots:
            if shot.shot_type not in VALID_SHOT_TYPES:
                bad_types.append((shot.shot_id, shot.shot_type))
            if shot.camera_movement not in VALID_CAMERA_MOVEMENTS:
                bad_movements.append((shot.shot_id, shot.camera_movement))

    assert not bad_types, f"非法景别: {bad_types}"
    assert not bad_movements, f"非法运镜: {bad_movements}"


def test_shots_have_usable_visual_prompt_and_duration(real_screenplay):
    """原 check("visual_prompt length")/check("has duration")——下游视频模型的硬门槛。"""
    too_short = []
    bad_duration = []
    for scene in real_screenplay.scenes:
        for shot in scene.shots:
            if len(shot.visual_prompt) < 20:
                too_short.append((shot.shot_id, len(shot.visual_prompt)))
            if not shot.duration.endswith("s"):
                bad_duration.append((shot.shot_id, shot.duration))

    assert not too_short, f"visual_prompt 过短: {too_short}"
    assert not bad_duration, f"duration 格式错误: {bad_duration}"


def test_dialogue_fields_are_filled(real_screenplay):
    """原「dialogue has character / has line」检查。"""
    bad = [
        shot.shot_id
        for scene in real_screenplay.scenes
        for shot in scene.shots
        if shot.dialogue and (not shot.dialogue.character or not shot.dialogue.line)
    ]

    assert not bad, f"对白字段缺失的镜头: {bad}"


def test_dialogue_characters_exist_in_registry(real_screenplay):
    """
    原 check("dialogue characters in registry")——跨模块一致性。

    这条是全链路测试里最有价值的一类断言：它验证「对白引用的角色」与
    「全局角色字典」这两个由不同模块产出的数据集没有脱节。
    """
    dialogue_ids = {
        shot.dialogue.character_id
        for scene in real_screenplay.scenes
        for shot in scene.shots
        if shot.dialogue
    }
    registry_ids = {c.character_id for c in real_screenplay.characters}

    assert dialogue_ids.issubset(registry_ids), (
        f"对白引用了不存在的角色: {dialogue_ids - registry_ids}"
    )


# ============================================================
# 序列化与二次校验
# ============================================================

def test_screenplay_serializes_to_yaml(real_screenplay):
    """原 check("e2e yaml output")。"""
    yaml_str = SafeParser.screenplay_to_yaml(real_screenplay)

    assert len(yaml_str) > 100, f"yaml length: {len(yaml_str)}"


def test_screenplay_passes_pydantic_revalidation(real_screenplay):
    """原 check("e2e re-validation passes")——产出能无损穿过序列化边界。"""
    revalidated = Screenplay.model_validate(real_screenplay.model_dump())

    assert revalidated.model_dump() == real_screenplay.model_dump()
