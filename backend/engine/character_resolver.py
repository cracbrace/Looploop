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
        两阶段后处理去重：先 Python 硬合并，再 LLM 语义消歧。

        问题场景：77 个镜头的大文本中，"林震南" 在多个 Chunk 被 extractor
        独立提取，增量消歧无法跨批次归并，导致 C01、C06、C08 指向同一人。
        """
        logs = []
        if len(registry) <= 1:
            return registry, logs

        # ═══════════════════════════════════════════════════════
        # Phase 1: 代码级精确同名去重 (Exact Match)
        # 用 canonical_name 为 key 做确定性合并，无 LLM 参与。
        # ═══════════════════════════════════════════════════════
        name_to_id: dict[str, str] = {}     # canonical_name → 保留的 cid
        merged: dict[str, ResolvedCharacter] = {}

        for cid, char in registry.items():
            key = char.canonical_name.strip()
            if not key:
                continue
            if key not in name_to_id:
                # 首次出现 — 记录为基准条目
                name_to_id[key] = cid
                merged[cid] = char
            else:
                # 重复条目 — 合并到基准条目
                keeper_cid = name_to_id[key]
                keeper = merged[keeper_cid]
                keeper.aliases = list(set(keeper.aliases + char.aliases))
                if not keeper.description and char.description:
                    keeper.description = char.description
                if keeper.role_type == "supporting" and char.role_type != "supporting":
                    keeper.role_type = char.role_type
                if keeper.gender == "other" and char.gender != "other":
                    keeper.gender = char.gender
                if keeper.age_range == "unknown" and char.age_range != "unknown":
                    keeper.age_range = char.age_range
                logs.append(f'[CharacterResolver] Phase1 同名合并: "{key}" ({cid}→{keeper_cid})')

        if len(merged) <= 1:
            return self._renumber(merged), logs

        # ═══════════════════════════════════════════════════════
        # Phase 2: LLM 语义消歧 (Semantic Match)
        # 传入 LLM 的名单中每个 canonical_name 唯一。
        # LLM 返回的是 canonical_name 组成的 merge_groups。
        # 解析时用 name_to_id 字典定位 cid，彻底杜绝重名误杀。
        # ═══════════════════════════════════════════════════════
        # 重建 name_to_id（Phase 1 可能改变了映射）
        name_to_id = {}
        id_to_name: dict[str, str] = {}
        for cid, char in merged.items():
            key = char.canonical_name.strip()
            name_to_id[key] = cid
            id_to_name[cid] = key

        names_list = [
            {"id": cid, "name": char.canonical_name, "aliases": char.aliases}
            for cid, char in merged.items()
        ]

        try:
            prompt = f"""以下是一部小说提取后的所有唯一角色。请判断是否有不同名字实际指向同一人。

角色列表（每个名字都是唯一的）：
{json.dumps(names_list, ensure_ascii=False, indent=2)}

注意：只合并你确信指向同一人的名字。例如小说中 "林教头" 和 "林震南" 是同一人，
"王队" 和 "王建国" 是同一人。如果你不确定，宁可保留不合并。

输出格式：
```json
{{"merge_groups": [["林震南", "林教头", "林总镖头"], ["王建国", "王队"]]}}
```"""

            result = await self.llm.generate_json(prompt, temperature=0.1)
            data = json.loads(result)
            merge_groups = data.get("merge_groups", [])

            for group in merge_groups:
                if len(group) < 2:
                    continue

                # 用 name_to_id 把所有名字映射到 cid（Phase 1 保证每个名字唯一）
                group_cids: list[str] = []
                for name in group:
                    n = name.strip()
                    cid = name_to_id.get(n)
                    if cid and cid not in group_cids:
                        group_cids.append(cid)

                if len(group_cids) < 2:
                    continue

                # 第一个 cid 作为主条目，其余合并进去后删除
                primary_cid = group_cids[0]
                primary_char = merged.get(primary_cid)
                if not primary_char:
                    continue

                for dup_cid in group_cids[1:]:
                    dup_char = merged.get(dup_cid)
                    if not dup_char:
                        continue
                    # 合并 aliases
                    primary_char.aliases.append(dup_char.canonical_name)
                    primary_char.aliases.extend(dup_char.aliases)
                    primary_char.aliases = list(set(primary_char.aliases))
                    # 合并属性
                    if not primary_char.description and dup_char.description:
                        primary_char.description = dup_char.description
                    if primary_char.role_type == "supporting" and dup_char.role_type != "supporting":
                        primary_char.role_type = dup_char.role_type
                    # 删除重复条目
                    del merged[dup_cid]
                    logs.append(
                        f'[CharacterResolver] Phase2 语义合并: '
                        f'"{dup_char.canonical_name}" → "{primary_char.canonical_name}" ({dup_cid}→{primary_cid})'
                    )

        except Exception as e:
            logs.append(f'[CharacterResolver] Phase2 LLM跳过: {e}')

        # 重新编号
        return self._renumber(merged), logs

    def _renumber(self, merged: dict[str, ResolvedCharacter]) -> dict[str, ResolvedCharacter]:
        """重新分配连续 ID，清理空别名"""
        final: dict[str, ResolvedCharacter] = {}
        for i, (_, char) in enumerate(merged.items()):
            cid = f"char_{i:03d}"
            char.aliases = [a for a in set(char.aliases) if a.strip() and a != char.canonical_name]
            final[cid] = char
        return final

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
