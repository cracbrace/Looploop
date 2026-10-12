"""
L2 集成：ChapterExtractor × CharacterResolver.registry 的联合调用。

迁移对照（backend/test_pipeline.py → 本文件）：
    test_extractor_with_registry
        → test_registry_holds_real_resolved_character_objects
          test_resolve_alias[小叶|雷政委|叶老师|unknown]
          test_build_prompt_context_contains_registry_entries
          test_extractor_prompt_builds_with_real_registry_objects   ← Bug 1 回归
          test_extractor_prompt_accepts_dict_registry                ← 另一分支

本文件的核心价值：**docs/Testing_Lessons.md#Bug-1 的回归固化**。

Bug 1 原貌：`extractor._build_extraction_prompt()` 对 registry 的每个值先调 `.get()`
（dict 方法）再判断 `isinstance(char, dict)`；当值是 `ResolvedCharacter` dataclass 时抛
`'ResolvedCharacter' object has no attribute 'get'`。

它当时漏网的原因不是「没测 registry」，而是「从没让 registry 穿过模块边界」——
旧测试只验证了 ResolvedCharacter 自身字段，因此下面的联合调用用例才是真正的护栏。
"""

from __future__ import annotations

import pytest

from backend.engine.character_resolver import CharacterResolver
from backend.engine.extractor import ChapterExtractor


# ============================================================
# registry 的数据契约
# ============================================================

def test_registry_holds_real_resolved_character_objects(registry):
    """registry 的值必须是可直接属性访问的真实对象——这是 Bug 1 的类型契约。"""
    char = registry["char_000"]

    assert char.canonical_name == "叶文洁", f"got {char.canonical_name}"
    assert "小叶" in char.aliases, f"aliases: {char.aliases}"
    assert not isinstance(char, dict), "registry 里混进了 dict 替身，Bug 1 会因此漏测"


@pytest.mark.parametrize(
    "name, expected",
    [
        ("小叶", "叶文洁"),
        ("雷政委", "雷志成"),
        ("叶老师", "叶文洁"),
        ("unknown", None),
    ],
    ids=["alias-xiaoye", "alias-leizhengwei", "alias-yelaoshi", "unknown-name"],
)
def test_resolve_alias(name, expected, registry):
    """别名 → canonical_name；查不到返回 None（merger 依赖这个契约做回落）。"""
    resolver = CharacterResolver(None)

    assert resolver.resolve_alias(name, registry) == expected


def test_build_prompt_context_contains_registry_entries(registry):
    """注入 LLM 的全局角色表必须带上 ID / 规范名 / 别名。"""
    context = CharacterResolver(None).build_prompt_context(registry)

    assert len(context) > 0, "prompt context is empty"
    assert "叶文洁" in context
    assert "小叶" in context
    assert "char_000" in context


# ============================================================
# Bug 1 回归：registry 穿过模块边界的联合路径
# ============================================================

def test_extractor_prompt_builds_with_real_registry_objects(registry):
    """
    回归 docs/Testing_Lessons.md#Bug-1。

    把真实 ResolvedCharacter registry 直接灌进 extractor 的 prompt 构建路径。
    若有人把 `isinstance(char, dict)` 判断挪到 `.get()` 之后（Bug 1 的原始写法），
    本用例会以 AttributeError 变红——这正是它存在的意义。
    """
    prompt = ChapterExtractor(None)._build_extraction_prompt("叶文洁抬头望向星空。", registry)

    assert "叶文洁" in prompt, "registry 未注入 prompt"
    assert "小叶" in prompt, "别名未注入 prompt"
    assert "雷政委" in prompt, "第二个角色未注入 prompt"


def test_extractor_prompt_accepts_dict_registry():
    """
    `isinstance(char, dict)` 的另一侧分支。

    registry 允许是 dict 形态（兼容早期调用与外部 JSON），这条分支同样不能坏。
    """
    dict_registry = {
        "char_000": {
            "canonical_name": "叶文洁",
            "aliases": ["小叶"],
            "description": "年轻女物理学家",
        }
    }

    prompt = ChapterExtractor(None)._build_extraction_prompt("叶文洁抬头望向星空。", dict_registry)

    assert "叶文洁" in prompt, "dict 形态 registry 未被识别"
    assert "小叶" in prompt, "dict 形态 registry 的别名未注入"


def test_extractor_prompt_without_registry():
    """
    registry 为 None 时不应注入角色表区块，也不应抛异常。

    注意断言锚定的是区块标题 `## 已知角色表`——prompt 的输出格式模板里本来就含
    「已知角色表」四个字（characters_found 的说明），只匹配这四个字会永远为真。
    """
    prompt = ChapterExtractor(None)._build_extraction_prompt("叶文洁抬头望向星空。", None)

    assert "## 已知角色表" not in prompt, "无 registry 时不应出现角色表区块"
    assert "叶文洁抬头望向星空。" in prompt, "待处理文本未注入"
