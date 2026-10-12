"""
L3 端到端：空文本必须被优雅拒绝。

迁移自 backend/test_pipeline.py::test_pipeline_empty_text。

⚠ 相对 PR 计划的一处改进（已在 PR 描述中标注）：
计划原文要求本用例「同样标记 llm」。但空文本在 `run_pipeline()` 的
「文本切分」阶段就抛 ValueError，**根本走不到 LLM**——
把它标成 llm 只会让它在 CI 里被 skip 掉，白白丢掉一条零成本的护栏。

因此这里改为离线用例，并用 `_ExplodingLLM` 把「不该调用 LLM」变成硬断言：
一旦空文本路径真的去调 LLM，测试立刻以 AssertionError 失败，
而不是悄悄花掉一次 API 调用。
"""

from __future__ import annotations

import pytest

from backend.engine.pipeline import Pipeline


class _ExplodingLLM:
    """
    「一旦被使用就爆炸」的 LLM 替身。

    用途不是模拟正常返回，而是断言**某条路径完全不该触达 LLM**。
    这比断言「返回了某个东西」更强：它把「无谓调用」也纳入失败范围。
    """

    async def generate_json(self, *args, **kwargs):
        raise AssertionError("空文本路径不应调用 LLM（generate_json）")

    async def generate_text(self, *args, **kwargs):
        raise AssertionError("空文本路径不应调用 LLM（generate_text）")


async def test_empty_text_is_rejected():
    """空文本 → 切分阶段抛 ValueError，且全程不碰 LLM。"""
    pipeline = Pipeline(_ExplodingLLM())  # type: ignore[arg-type]

    with pytest.raises(ValueError, match="切分"):
        async for _ in pipeline.run_pipeline(""):
            pass


async def test_whitespace_only_text_is_rejected():
    """纯空白与空字符串等价——TextSplitter.split() 用 strip() 判空。"""
    pipeline = Pipeline(_ExplodingLLM())  # type: ignore[arg-type]

    with pytest.raises(ValueError, match="切分"):
        async for _ in pipeline.run_pipeline("   \n\n\t  "):
            pass
