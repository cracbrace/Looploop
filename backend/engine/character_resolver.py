"""
角色消歧模块

长篇小说中同一角色常有多个别名（"王建国" = "王队长" = "老王"）。
如果直接给 AI，下游会生成三个不同的虚拟演员。

此模块通过 LLM 语义理解 + 规则聚类，将所有别名收拢到唯一的 canonical_name，
构建全局 Character Registry，供后续所有 LLM 调用注入。
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field

from backend.llm_client import LLMClient


# ============================================================
# 数据结构
# ============================================================

@dataclass
class ResolvedCharacter:
    """消歧后的角色"""
    canonical_name: str        # 规范名称
    aliases: list[str]         # 所有别名
    description: str           # 一句话描述
    role_type: str             # protagonist/antagonist/supporting/cameo
    gender: str                # male/female/other
    age_range: str             # 如"25-30"
    first_appearance: str = ""  # 首次出场场景描述


# ============================================================
# 消歧器
# ============================================================

class CharacterResolver:
    """
    角色消歧器。

    分两轮处理：
    第一轮：LLM 从全文中提取所有人物名和可能的别名映射
    第二轮：规则合并 + LLM 二次确认不确定的候选对
    """

    SYSTEM_PROMPT = """你是一位文学分析和人物图谱专家。

你的任务是从小说文本中提取所有出场人物，并为每个人物标注所有别名。

## 输出要求

1. 对每个人物，给出：
   - canonical_name：你认为最正式、最规范的名字
   - aliases：文本中出现的该人物的所有别名（包括简称、职称、昵称等）
   - description：一句话描述该人物的身份和性格
   - role_type：protagonist（主角）/ antagonist（反派）/ supporting（配角）/ cameo（龙套）
   - gender：male / female / other
   - age_range：年龄范围，如"25-30"或"50+"，无法判断则"unknown"
   - first_appearance：首次出场的场景简述

2. 特别注意以下别名模式：
   - 姓氏 + 职务："王队长"、"李工程师"、"雷政委"
   - 老/小 + 姓氏："老王"、"小叶"、"老赵头"
   - 名字简称："文洁"（叶文洁的简称）、"建国"（王建国的名）
   - 亲属/关系称谓：如果文本中有，也请标注
   - 同音/谐音：如可能，请标注

3. 如果两个人名确实指向同一人，将它们合并到一个条目下。
4. 如果无法确定是否同一人，宁可分开标注 different，不要强行合并。"""

    def __init__(self, llm: LLMClient):
        self.llm = llm

    # ============================================================
    # 公开接口
    # ============================================================

    async def resolve(
        self,
        text: str,
        characters_found: list[str] | None = None,
    ) -> dict[str, ResolvedCharacter]:
        """
        从全文提取并消歧角色。

        Args:
            text: 小说全文
            characters_found: extractor 在各段发现的角色名列表（增强信号）

        Returns:
            {character_id: ResolvedCharacter}
        """
        if not text.strip():
            return {}

        # 第一轮：LLM 提取角色 + 别名映射
        raw_characters = await self._extract_characters(text, characters_found)

        # 第二轮：规则合并 + LLM 确认
        merged = await self._merge_and_confirm(raw_characters, text)

        # 构建 registry
        registry = {}
        for i, char in enumerate(merged):
            char_id = f"char_{i:03d}"
            registry[char_id] = char

        return registry

    def build_prompt_context(self, registry: dict[str, ResolvedCharacter]) -> str:
        """
        将 registry 格式化为可注入 LLM prompt 的字符串。

        用于 extractor 和 scene_merger 的 prompt 构建。
        """
        if not registry:
            return ""

        entries = []
        for cid, char in registry.items():
            aliases_str = "、".join(char.aliases) if char.aliases else "无"
            entries.append(
                f"| {cid} | {char.canonical_name} | {aliases_str} | "
                f"{char.role_type} | {char.gender} | {char.age_range} |"
            )

        header = (
            "## 全局角色表（请使用 canonical_name，不要使用别名）\n\n"
            "| ID | 规范名 | 别名 | 类型 | 性别 | 年龄 |\n"
            "|----|--------|------|------|------|------|\n"
        )
        return header + "\n".join(entries) + "\n"

    async def resolve_incremental(
        self,
        existing_registry: dict[str, ResolvedCharacter],
        new_characters: list[str],
        context_text: str = "",
    ) -> tuple[dict[str, ResolvedCharacter], list[str]]:
        """
        增量消歧：将新发现的角色合并到已有注册表中。

        每处理完几个 chunk 调用一次，渐进式构建角色字典。
        返回 (更新后的 registry, 日志消息列表)。

        Args:
            existing_registry: 当前已有的角色注册表
            new_characters: 本批 chunk 中新发现的角色名列表
            context_text: 本批 chunk 的文本片段（用于 LLM 消歧上下文）

        Returns:
            (updated_registry, log_messages)
        """
        logs = []
        if not new_characters:
            return existing_registry, logs

        # 过滤已在 registry 中的（canonical_name 或 aliases 匹配）
        truly_new = []
        for name in new_characters:
            name_clean = name.strip()
            if not name_clean:
                continue
            found = False
            for cid, char in existing_registry.items():
                if name_clean == char.canonical_name or name_clean in char.aliases:
                    found = True
                    break
            if not found:
                truly_new.append(name_clean)

        if not truly_new:
            return existing_registry, logs

        # 对真正新的角色做消歧
        # 快速规则：检查是否可能属于已有角色的别名
        for name in truly_new[:]:
            for cid, char in existing_registry.items():
                # 姓氏+职务匹配 (如 "王队" 已有 "王建国")
                if len(name) <= 3 and name[0] == char.canonical_name[0]:
                    # 用 LLM 确认
                    confirm = await self._confirm_alias(name, char.canonical_name, context_text)
                    if confirm:
                        char.aliases.append(name)
                        char.aliases = list(set(char.aliases))
                        logs.append(f'[CharacterResolver] 合并 "{name}" → "{char.canonical_name}" ({cid})')
                        truly_new.remove(name)
                        break

        # 对于仍无法匹配的，作为全新角色添加
        for name in truly_new:
            cid = f"char_{len(existing_registry):03d}"
            existing_registry[cid] = ResolvedCharacter(
                canonical_name=name,
                aliases=[],
                description="",
                role_type="supporting",
                gender="other",
                age_range="unknown",
            )
            logs.append(f'[CharacterResolver] 新增角色: "{name}" ({cid})')

        return existing_registry, logs

    async def deduplicate(
        self,
        registry: dict[str, ResolvedCharacter],
        full_text: str = "",
    ) -> tuple[dict[str, ResolvedCharacter], list[str]]:
        """
        后处理去重：扫描 registry 中指向同一人的重复条目并合并。

        问题场景：77 个镜头的大文本中，"林震南" 在多个 Chunk 被 extractor
        独立提取。增量消歧只在每批 3 个 Chunk 后运行，无法跨越批次做全局归并。
        导致同一角色被分配 C01、C06、C08 等多个 ID。

        修复策略：
        1. 先按 canonical_name 做精确匹配去重（同名不同 ID 直接合并）
        2. 再用 LLM 对整个 registry 做一次全局消歧（判断不同名是否同一人）
        3. 最后用规则 clean up（移除空别名等）
        """
        logs = []
        if len(registry) <= 1:
            return registry, logs

        # Step 1: 精确同名去重 — canonical_name 完全相同的条目合并 aliases
        merged: dict[str, ResolvedCharacter] = {}
        for cid, char in registry.items():
            key = char.canonical_name.strip()
            if not key:
                continue
            if key not in merged:
                merged[cid] = char
            else:
                # 同名：合并 aliases，保留信息更丰富的条目
                existing = merged[cid]
                existing.aliases = list(set(existing.aliases + char.aliases))
                if not existing.description and char.description:
                    existing.description = char.description
                if existing.role_type == "supporting" and char.role_type != "supporting":
                    existing.role_type = char.role_type
                if existing.gender == "other" and char.gender != "other":
                    existing.gender = char.gender
                if existing.age_range == "unknown" and char.age_range != "unknown":
                    existing.age_range = char.age_range
                logs.append(f'[CharacterResolver] 去重合并: 同名 "{key}" 的两个条目已合并 ({cid})')

        # Step 2: LLM 全局消歧 — 识别不同 canonical_name 但指向同一人的情况
        if len(merged) >= 2:
            names_list = [
                {"id": cid, "name": char.canonical_name, "aliases": char.aliases}
                for cid, char in merged.items()
            ]
            try:
                prompt = f"""以下是从一部小说中提取的所有角色。请检查是否有不同条目指向同一个人。

角色列表：
{json.dumps(names_list, ensure_ascii=False, indent=2)}

请仔细判断：如果两个名字指向同一人（如"林教头"和"林震南"指同一人，"王队"和"王建国"指同一人），请将它们标记为同一组。

输出格式：
```json
{{"merge_groups": [["林震南", "林教头", "林总镖头"], ["王建国", "王队"]]}}
```

只输出确定指向同一人的组。如果不确定，宁可保留不合并。"""

                result = await self.llm.generate_json(prompt, temperature=0.1)
                data = json.loads(result)
                merge_groups = data.get("merge_groups", [])

                for group in merge_groups:
                    if len(group) < 2:
                        continue
                    # 找到组内第一个在 registry 中的条目的 cid，作为主条目
                    primary_name = group[0].strip()
                    primary_cid = None
                    for cid, char in merged.items():
                        if char.canonical_name.strip() == primary_name:
                            primary_cid = cid
                            break
                    if not primary_cid:
                        continue

                    # 将组内其他名字合并到主条目
                    for alias_name in group[1:]:
                        alias_clean = alias_name.strip()
                        for cid, char in list(merged.items()):
                            if char.canonical_name.strip() == alias_clean:
                                merged[primary_cid].aliases.append(alias_clean)
                                merged[primary_cid].aliases = list(set(merged[primary_cid].aliases))
                                del merged[cid]
                                logs.append(f'[CharacterResolver] LLM消歧合并: "{alias_clean}" → "{primary_name}"')
                                break

            except Exception as e:
                logs.append(f'[CharacterResolver] LLM全局消歧跳过: {e}')

        # Step 3: 重新编号
        final: dict[str, ResolvedCharacter] = {}
        for i, (_, char) in enumerate(merged.items()):
            cid = f"char_{i:03d}"
            char.aliases = [a for a in set(char.aliases) if a.strip() and a != char.canonical_name]
            final[cid] = char

        return final, logs

    async def _confirm_alias(self, alias: str, canonical: str, context: str) -> bool:
        """用 LLM 判断 alias 是否是 canonical 的别名"""
        prompt = f"""在以下上下文中，"{
        alias}" 和 "{canonical}" 是否指向同一个人？

上下文：{context[:300]}

请只输出 JSON: {{"same_person": true}} 或 {{"same_person": false}}"""
        try:
            result = await self.llm.generate_json(prompt, temperature=0.1)
            import json
            return json.loads(result).get("same_person", False)
        except Exception:
            # 简单启发式：姓氏相同 + 字符数 ≤ 3 → 可能是别名
            return len(alias) <= 3 and alias[0] == canonical[0]

    def resolve_alias(self, name: str, registry: dict[str, ResolvedCharacter]) -> str | None:
        """
        将角色名（可能是别名）解析为 canonical_name。

        Args:
            name: 可能是别名或规范名
            registry: 角色字典

        Returns:
            canonical_name，如果找不到匹配则返回 None
        """
        name_clean = name.strip()
        if not name_clean:
            return None

        for cid, char in registry.items():
            if name_clean == char.canonical_name:
                return name_clean
            if name_clean in char.aliases:
                return char.canonical_name

        return None

    # ============================================================
    # 内部方法
    # ============================================================

    async def _extract_characters(
        self,
        text: str,
        characters_found: list[str] | None = None,
    ) -> list[dict]:
        """第一轮：LLM 提取角色信息"""
        extra_hint = ""
        if characters_found:
            unique_names = list(set(characters_found))
            extra_hint = (
                "\n\n## 辅助信息\n"
                f"从文本中已发现的名字列表（可能包含重复和别名）："
                f"{', '.join(unique_names)}\n"
                f"请对这些名字做消歧和归类。\n"
            )

        prompt = f"""请分析以下小说文本，提取所有人物并标注别名。

{text}
{extra_hint}

请输出以下格式的 JSON：

```json
{{
  "characters": [
    {{
      "canonical_name": "叶文洁",
      "aliases": ["叶老师", "小叶", "文洁"],
      "description": "年轻的女天体物理学家，孤独而执着",
      "role_type": "protagonist",
      "gender": "female",
      "age_range": "25-30",
      "first_appearance": "红岸基地山顶"
    }}
  ]
}}
```

只输出合法 JSON。"""

        raw_json = await self.llm.generate_json(
            prompt=prompt,
            system_prompt=self.SYSTEM_PROMPT,
            temperature=0.3,
        )

        data = json.loads(raw_json)
        return data.get("characters", [])

    async def _merge_and_confirm(
        self,
        raw_characters: list[dict],
        text: str,
    ) -> list[ResolvedCharacter]:
        """第二轮：合并高置信度匹配 + LLM 确认不确定项"""
        if len(raw_characters) <= 1:
            return [self._to_resolved_char(c) for c in raw_characters]

        # 简单规则合并：如果 canonical_name 完全相同，直接合并 aliases
        merged_map: dict[str, dict] = {}
        for char in raw_characters:
            key = char.get("canonical_name", "").strip()
            if not key:
                continue
            if key not in merged_map:
                merged_map[key] = dict(char)
                merged_map[key]["aliases"] = list(set(char.get("aliases", [])))
            else:
                # 合并 aliases
                existing = set(merged_map[key].get("aliases", []))
                new_aliases = set(char.get("aliases", []))
                merged_map[key]["aliases"] = list(existing | new_aliases)

        # 对相似但不同名的做一次 LLM 二次确认
        names = list(merged_map.keys())
        if len(names) >= 2:
            confirm_prompt = f"""以下是从一部小说中提取的角色列表。请检查是否有不同条目指向同一个人，需要合并。

角色列表：
{json.dumps([{"name": n, "aliases": merged_map[n]["aliases"]} for n in names], ensure_ascii=False, indent=2)}

规则：
- 庄重的规范名 vs 口语化的简称通常指向同一人（如"叶文洁"和"小叶"）
- 但是不同姓氏的角色即使职务相同也是不同人（如"李工程师"和"王工程师"）
- 如果不确定，宁可保留不合并

请输出需要合并的组（每组是同一人）：
```json
{{
  "merge_groups": [
    ["叶文洁", "叶老师"],
    ["王建国", "王队长"]
  ]
}}
```
如果没有需要合并的，返回空数组。"""

            try:
                result = await self.llm.generate_json(
                    prompt=confirm_prompt,
                    temperature=0.2,
                )
                confirm_data = json.loads(result)
                merge_groups = confirm_data.get("merge_groups", [])

                # 执行合并
                for group in merge_groups:
                    if len(group) < 2:
                        continue
                    primary = group[0]
                    if primary not in merged_map:
                        continue
                    for alias_name in group[1:]:
                        if alias_name in merged_map and alias_name != primary:
                            merged_map[primary]["aliases"].extend(
                                merged_map[alias_name].get("aliases", [])
                            )
                            merged_map[primary]["aliases"].append(alias_name)
                            del merged_map[alias_name]

            except Exception:
                pass  # 确认失败不阻塞流程

        # 去重 aliases
        for name in merged_map:
            merged_map[name]["aliases"] = list(set(
                a for a in merged_map[name].get("aliases", [])
                if a != name
            ))

        return [self._to_resolved_char(c) for c in merged_map.values()]

    @staticmethod
    def _to_resolved_char(data: dict) -> ResolvedCharacter:
        """dict → ResolvedCharacter"""
        return ResolvedCharacter(
            canonical_name=data.get("canonical_name", ""),
            aliases=data.get("aliases", []),
            description=data.get("description", ""),
            role_type=data.get("role_type", "supporting"),
            gender=data.get("gender", "other"),
            age_range=data.get("age_range", "unknown"),
            first_appearance=data.get("first_appearance", ""),
        )
