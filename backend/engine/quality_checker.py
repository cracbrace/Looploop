"""
质检报告模块

对生成的 Screenplay 做自动质量检查，输出结构化报告。
帮助作者和 LLM 在编辑前发现潜在问题。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from collections import Counter

from backend.models import Screenplay, Scene, Shot


# ============================================================
# 数据结构
# ============================================================

@dataclass
class Issue:
    """一个质量问题"""
    severity: str       # "error" | "warning" | "info"
    type: str           # 问题类型标识
    message: str        # 人类可读的描述
    location: str       # 定位信息（场景/镜头）


@dataclass
class CharacterStat:
    """角色统计"""
    character_id: str
    canonical_name: str
    total_appearances: int     # 出场镜头数
    total_lines: int           # 台词句数
    scene_ids: list[str]       # 出场的场景 ID 列表
    first_scene: str = ""      # 首次出场场景


@dataclass
class SceneDuration:
    """场景时长"""
    scene_id: str
    scene_number: int
    location: str
    duration_estimate: str
    shot_count: int


@dataclass
class QualityReport:
    """质检报告"""
    # 统计
    character_stats: list[CharacterStat] = field(default_factory=list)
    shot_type_distribution: dict[str, int] = field(default_factory=dict)
    camera_movement_distribution: dict[str, int] = field(default_factory=dict)
    scene_duration_breakdown: list[SceneDuration] = field(default_factory=list)

    # 问题
    issues: list[Issue] = field(default_factory=list)

    # 摘要
    total_scenes: int = 0
    total_shots: int = 0
    total_characters: int = 0
    total_dialogue_shots: int = 0       # 有对白的镜头数
    silent_shot_ratio: float = 0.0      # 无对白镜头比例

    @property
    def issue_count(self) -> int:
        return len(self.issues)

    @property
    def error_count(self) -> int:
        return sum(1 for i in self.issues if i.severity == "error")

    @property
    def warning_count(self) -> int:
        return sum(1 for i in self.issues if i.severity == "warning")


# ============================================================
# 质检器
# ============================================================

class QualityChecker:
    """
    剧本自动质检器。

    检测项包括：
    - 角色出场的合理性（单次出场、未使用角色）
    - 镜头语言的多样性
    - 无对白镜头的连续性
    - visual_prompt 的质量
    """

    def check(self, screenplay: Screenplay) -> QualityReport:
        """对 Screenplay 做全面质量检查"""
        report = QualityReport(
            total_scenes=screenplay.meta.total_scenes,
            total_shots=screenplay.meta.total_shots,
            total_characters=len(screenplay.characters),
        )

        # 收集所有镜头
        all_shots = []
        for scene in screenplay.scenes:
            all_shots.extend(scene.shots)

        # 1. 镜头类型分布
        shot_types = Counter(s.shot_type for s in all_shots)
        report.shot_type_distribution = dict(shot_types)

        # 2. 运镜分布
        movements = Counter(s.camera_movement for s in all_shots)
        report.camera_movement_distribution = dict(movements)

        # 3. 场景时长拆解
        for scene in screenplay.scenes:
            report.scene_duration_breakdown.append(SceneDuration(
                scene_id=scene.scene_id,
                scene_number=scene.scene_number,
                location=scene.location,
                duration_estimate=scene.duration_estimate,
                shot_count=len(scene.shots),
            ))

        # 4. 角色统计
        character_id_to_name = {
            c.character_id: c.canonical_name
            for c in screenplay.characters
        }

        # 初始化所有角色统计
        char_stats: dict[str, CharacterStat] = {}
        for c in screenplay.characters:
            char_stats[c.character_id] = CharacterStat(
                character_id=c.character_id,
                canonical_name=c.canonical_name,
                total_appearances=0,
                total_lines=0,
                scene_ids=[],
            )

        for scene in screenplay.scenes:
            for shot in scene.shots:
                if shot.dialogue:
                    cid = shot.dialogue.character_id
                    if cid in char_stats:
                        char_stats[cid].total_lines += 1
                        if scene.scene_id not in char_stats[cid].scene_ids:
                            char_stats[cid].scene_ids.append(scene.scene_id)

        # 统计出场次数（有 dialogue 的 shot）
        for cid, stat in char_stats.items():
            stat.total_appearances = stat.total_lines
            if stat.scene_ids:
                stat.first_scene = stat.scene_ids[0]

        report.character_stats = list(char_stats.values())

        # 5. 对白统计
        dialogue_shots = [s for s in all_shots if s.dialogue]
        report.total_dialogue_shots = len(dialogue_shots)
        report.silent_shot_ratio = (
            1.0 - len(dialogue_shots) / len(all_shots)
        ) if all_shots else 0.0

        # ============================================================
        # 问题检测
        # ============================================================

        issues = []

        # --- 角色问题 ---
        for stat in char_stats.values():
            if stat.total_lines == 0:
                issues.append(Issue(
                    severity="warning",
                    type="unused_character",
                    message=f"角色「{stat.canonical_name}」在剧本中无任何台词",
                    location=f"character:{stat.character_id}",
                ))
            elif stat.total_lines == 1:
                issues.append(Issue(
                    severity="info",
                    type="single_line_character",
                    message=f"角色「{stat.canonical_name}」仅有 1 句台词，请确认是否为有效角色",
                    location=f"character:{stat.character_id}",
                ))

        # --- 镜头多样性 ---
        if len(shot_types) <= 1 and len(all_shots) >= 3:
            issues.append(Issue(
                severity="warning",
                type="monotonous_shot_type",
                message=f"全剧本仅使用了 {len(shot_types)} 种景别，可能导致视觉单调",
                location="global",
            ))

        if len(movements) <= 1 and len(all_shots) >= 3:
            issues.append(Issue(
                severity="info",
                type="monotonous_camera_movement",
                message=f"全剧本仅使用了 {len(movements)} 种运镜方式，建议增加变化",
                location="global",
            ))

        # --- 连续无对白 ---
        silent_streak = 0
        max_silent_streak = 0
        for shot in all_shots:
            if shot.dialogue is None:
                silent_streak += 1
                max_silent_streak = max(max_silent_streak, silent_streak)
            else:
                silent_streak = 0

        if max_silent_streak >= 5:
            issues.append(Issue(
                severity="info",
                type="long_silent_streak",
                message=f"存在连续 {max_silent_streak} 个镜头无对白，可能导致节奏过闷",
                location="global",
            ))

        # --- 每场景镜头数检查 ---
        for scene in screenplay.scenes:
            shot_count = len(scene.shots)
            if shot_count == 1:
                issues.append(Issue(
                    severity="info",
                    type="single_shot_scene",
                    message=f"场景「{scene.location}」仅 1 个镜头，可能是提取不完整",
                    location=f"scene:{scene.scene_id}",
                ))
            # 检查场景内是否只有一种镜头类型
            scene_types = set(s.shot_type for s in scene.shots)
            if len(scene_types) == 1 and shot_count >= 3:
                issues.append(Issue(
                    severity="info",
                    type="scene_single_shot_type",
                    message=f"场景「{scene.location}」内全部为「{list(scene_types)[0]}」，建议增加变化",
                    location=f"scene:{scene.scene_id}",
                ))

        # --- visual_prompt 质量 ---
        short_prompts = 0
        for scene in screenplay.scenes:
            for shot in scene.shots:
                if len(shot.visual_prompt) < 50:
                    short_prompts += 1
        if short_prompts > 0:
            issues.append(Issue(
                severity="info" if short_prompts < len(all_shots) * 0.3 else "warning",
                type="short_visual_prompt",
                message=f"{short_prompts}/{len(all_shots)} 个镜头的 visual_prompt 较短（<50 字符），视频模型可能生成质量不足",
                location="global",
            ))

        # --- duration 合理性 ---
        too_short = sum(1 for s in all_shots if s.duration in ("1s", "2s"))
        if too_short > len(all_shots) * 0.3:
            issues.append(Issue(
                severity="info",
                type="too_many_short_shots",
                message=f"{too_short} 个镜头时长 ≤2s，可能导致成片过于碎片化",
                location="global",
            ))

        report.issues = issues
        return report
