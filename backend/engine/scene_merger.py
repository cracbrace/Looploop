"""
场景合并模块

将逐段提取产生的 RawScene 合并为最终 Scene：
- 相邻同地点同时间的场景归并
- 角色名统一化（别名→canonical_name）
- 镜头/场景编号重排
"""

from __future__ import annotations

from backend.engine.extractor import RawScene, RawShot
from backend.engine.character_resolver import CharacterResolver, ResolvedCharacter
from backend.models import (
    Scene,
    Shot,
    Dialogue,
    Character,
    Meta,
    Screenplay,
)


class SceneMerger:
    """
    场景合并器。

    职责：
    1. 合并相邻同地点场景
    2. 别名 → canonical_name 替换
    3. 生成最终 Pydantic Screenplay
    """

    def __init__(self, resolver: CharacterResolver | None = None):
        self.resolver = resolver

    # ============================================================
    # 公开接口
    # ============================================================

    def merge(
        self,
        raw_scenes: list[RawScene],
        registry: dict[str, ResolvedCharacter],
    ) -> list[Scene]:
        """
        合并 RawScene 列表为最终 Scene 列表。

        Args:
            raw_scenes: extractor 产出的所有 RawScene
            registry: CharacterResolver 产出的角色字典

        Returns:
            合并后的 Scene 列表（Pydantic 模型）
        """
        if not raw_scenes:
            return []

        # Step 1: 相邻同地点场景合并
        merged_raw = self._merge_adjacent(raw_scenes)

        # Step 2: 角色名统一化 + 构建 Pydantic Shot
        scenes = []
        for raw in merged_raw:
            shots = []
            for rs in raw.shots:
                shots.append(self._to_pydantic_shot(rs, registry))

            scenes.append(Scene(
                scene_id="s00",       # placeholder，后续重排
                scene_number=1,       # placeholder，后续重排
                location=raw.location,
                time_of_day=self._normalize_time_of_day(raw.time_of_day),
                era=raw.era if raw.era else None,
                atmosphere=raw.atmosphere,
                weather=raw.weather if raw.weather else None,
                duration_estimate=raw.duration_estimate,
                source_paragraphs=list(set(raw.source_paragraphs)),
                shots=shots,
            ))

        # Step 3: 编号重排（同时生成 material_id）
        for si, scene in enumerate(scenes):
            scene.scene_id = f"s{si + 1:02d}"
            scene.material_id = f"S{si + 1:02d}"
            scene.scene_number = si + 1
            for sji, shot in enumerate(scene.shots):
                shot.shot_id = f"{scene.scene_id}_{sji + 1:02d}"
                shot.shot_number = sji + 1

        return scenes

    def build_screenplay(
        self,
        scenes: list[Scene],
        registry: dict[str, ResolvedCharacter],
        meta_overrides: dict | None = None,
    ) -> Screenplay:
        """
        从合并后的 Scene 列表构建最终 Screenplay。

        Args:
            scenes: merge() 产出的 Scene 列表
            registry: 角色字典
            meta_overrides: Meta 字段覆盖（如 title、author 等）

        Returns:
            完整的 Screenplay 对象
        """
        # 转换角色 (生成 material_id: C01, C02...)
        characters = []
        char_index = 0
        for cid, rc in registry.items():
            char_index += 1
            characters.append(Character(
                character_id=cid,
                material_id=f"C{char_index:02d}",
                canonical_name=rc.canonical_name,
                aliases=rc.aliases,
                description=rc.description,
                role_type=self._normalize_role_type(rc.role_type),
                gender=self._normalize_gender(rc.gender),
                age_range=rc.age_range,
            ))

        # 统计
        total_shots = sum(len(s.shots) for s in scenes)
        total_seconds = 0
        for s in scenes:
            for sh in s.shots:
                dur = sh.duration.replace("s", "")
                try:
                    total_seconds += int(dur)
                except ValueError:
                    total_seconds += 5  # 默认 5 秒

        minutes = total_seconds // 60
        seconds = total_seconds % 60
        if minutes > 0:
            total_duration = f"{minutes}min{seconds}s"
        else:
            total_duration = f"{seconds}s"

        # 构建 Meta
        meta_data = {
            "title": meta_overrides.get("title", "Untitled") if meta_overrides else "Untitled",
            "source": meta_overrides.get("source", "Untitled") if meta_overrides else "Untitled",
            "author": meta_overrides.get("author", "Unknown") if meta_overrides else "Unknown",
            "genre": meta_overrides.get("genre", "General") if meta_overrides else "General",
            "total_scenes": len(scenes),
            "total_shots": total_shots,
            "total_duration_estimate": total_duration,
        }
        if meta_overrides:
            meta_data.update(meta_overrides)

        return Screenplay(
            meta=Meta(**meta_data),
            characters=characters,
            scenes=scenes,
        )

    # ============================================================
    # 内部方法
    # ============================================================

    def _merge_adjacent(self, raw_scenes: list[RawScene]) -> list[RawScene]:
        """合并相邻同地点同时间的场景"""
        if len(raw_scenes) <= 1:
            return raw_scenes

        merged = []
        current = raw_scenes[0]

        for next_scene in raw_scenes[1:]:
            if self._should_merge(current, next_scene):
                # 合并
                current.shots.extend(next_scene.shots)
                current.source_paragraphs = list(set(
                    current.source_paragraphs + next_scene.source_paragraphs
                ))
                # 合并 atmosphere（取更长的）
                if len(next_scene.atmosphere) > len(current.atmosphere):
                    current.atmosphere = next_scene.atmosphere
                # 合并 duration
                current.duration_estimate = self._merge_duration(
                    current.duration_estimate, next_scene.duration_estimate
                )
            else:
                merged.append(current)
                current = next_scene

        merged.append(current)
        return merged

    def _should_merge(self, a: RawScene, b: RawScene) -> bool:
        """判断两个场景是否应该合并"""
        # 同地点
        if a.location.strip() != b.location.strip():
            return False
        # 同时间
        if a.time_of_day.strip() != b.time_of_day.strip():
            return False
        # 不是跨章节（source_paragraphs 不连续跳太远）
        if a.source_paragraphs and b.source_paragraphs:
            a_max = max(a.source_paragraphs)
            b_min = min(b.source_paragraphs)
            if b_min - a_max > 5:  # 段落跳跃 > 5，可能是不同的时间点
                return False
        return True

    def _to_pydantic_shot(
        self,
        raw: RawShot,
        registry: dict[str, ResolvedCharacter],
    ) -> Shot:
        """RawShot → Pydantic Shot，同时做角色名统一化"""
        # 角色名统一化
        character_canonical = ""
        character_id = ""
        if raw.character and self.resolver:
            canonical = self.resolver.resolve_alias(raw.character, registry)
            if canonical:
                character_canonical = canonical
                # 反向查找 character_id
                for cid, rc in registry.items():
                    if rc.canonical_name == canonical:
                        character_id = cid
                        break
            else:
                character_canonical = raw.character

        # 构建 Dialogue
        dialogue = None
        if raw.line.strip():
            dialogue = Dialogue(
                character=character_canonical or raw.character,
                character_id=character_id or "char_000",
                line=raw.line,
                emotion=raw.emotion or "neutral",
                delivery=raw.delivery if raw.delivery else None,
            )

        return Shot(
            shot_id="s00_00",  # placeholder，后续重排
            shot_number=1,     # placeholder，后续重排
            shot_type=self._normalize_shot_type(raw.shot_type),
            camera_movement=self._normalize_camera_movement(raw.camera_movement),
            focus_subject=raw.focus_subject,
            visual_prompt=raw.visual_prompt,
            background=raw.background if raw.background else None,
            dialogue=dialogue,
            sfx=raw.sfx if raw.sfx else None,
            bgm=raw.bgm if raw.bgm else None,
            duration=self._normalize_duration(raw.duration),
            source_paragraphs=raw.source_paragraphs,
        )

    # ============================================================
    # 规范化方法
    # ============================================================

    @staticmethod
    def _normalize_shot_type(st: str) -> str:
        """规范化景别"""
        valid = {
            "大远景", "远景", "中景", "近景", "特写", "大特写",
            "双人镜头", "过肩镜头",
        }
        if st in valid:
            return st
        # 模糊匹配
        st_clean = st.strip()
        for v in valid:
            if v in st_clean or st_clean in v:
                return v
        return "中景"  # 默认

    @staticmethod
    def _normalize_camera_movement(cm: str) -> str:
        """规范化运镜"""
        valid = {
            "固定", "推进", "拉远", "左摇", "右摇", "上摇", "下摇",
            "跟随", "环绕", "手持", "快速变焦",
        }
        if cm in valid:
            return cm
        cm_clean = cm.strip()
        for v in valid:
            if v in cm_clean or cm_clean in v:
                return v
        return "固定"  # 默认

    @staticmethod
    def _normalize_time_of_day(tod: str) -> str:
        """规范化时间"""
        tod_lower = tod.strip().lower()
        if "night" in tod_lower or "夜" in tod_lower:
            return "night"
        if "dawn" in tod_lower or "晨" in tod_lower or "黎" in tod_lower:
            return "dawn"
        if "dusk" in tod_lower or "黄" in tod_lower or "暮" in tod_lower:
            return "dusk"
        if "interior" in tod_lower or "室" in tod_lower:
            return "interior"
        return "day"

    @staticmethod
    def _normalize_role_type(rt: str) -> str:
        valid = {"protagonist", "antagonist", "supporting", "cameo"}
        return rt if rt in valid else "supporting"

    @staticmethod
    def _normalize_gender(g: str) -> str:
        valid = {"male", "female", "other"}
        return g if g in valid else "other"

    @staticmethod
    def _normalize_duration(d: str) -> str:
        """确保 duration 格式为 '{n}s'"""
        d_clean = d.strip().lower().replace(" ", "")
        if d_clean.endswith("s"):
            return d_clean
        # 尝试解析纯数字
        try:
            return f"{int(d_clean)}s"
        except ValueError:
            return "5s"

    @staticmethod
    def _merge_duration(a: str, b: str) -> str:
        """合并两个时长字符串"""
        try:
            sec_a = int(a.replace("s", ""))
        except ValueError:
            sec_a = 0
        try:
            sec_b = int(b.replace("s", ""))
        except ValueError:
            sec_b = 0
        return f"{sec_a + sec_b}s"
