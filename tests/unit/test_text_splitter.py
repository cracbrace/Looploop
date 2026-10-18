"""
L1 单元测试：TextSplitter 文本切分。

迁移对照（backend/test_pipeline.py → 本文件）：
    test_text_splitter_basic        → test_split_produces_chunks
                                      test_split_respects_token_budget
    test_text_splitter_edge_cases   → test_split_edge_case_chunk_counts[空字符串|纯空白|短文本]
                                      test_split_without_chapter_markers_uses_single_chapter
    test_paragraph_mapping          → test_paragraph_mapping_reports_entries
                                      test_paragraph_mapping_covers_leading_paragraphs

改写要点：check(name, cond) → assert + 失败信息；3 类边界合并为 parametrize。
"""

from __future__ import annotations

import pytest

from backend.engine.text_splitter import TextSplitter

# 与旧脚本一致：max_tokens=200；token 上界放宽 50 以吸收段落间 "\n\n" 连接符开销
MAX_TOKENS = 200
TOKEN_UPPER_BOUND = MAX_TOKENS + 50


@pytest.fixture
def splitter() -> TextSplitter:
    return TextSplitter(max_tokens=MAX_TOKENS, overlap_ratio=0.2)


# ============================================================
# basic
# ============================================================

def test_split_produces_chunks(splitter, sample_text):
    """原 check("produces chunks")：SAMPLE_TEXT 至少切出 1 段。"""
    chunks = splitter.split(sample_text)

    assert len(chunks) >= 1, f"got {len(chunks)} chunks"


def test_split_respects_token_budget(splitter, sample_text):
    """原 check("token budget")：每段 token 不超预算，否则送 LLM 会爆上下文。"""
    chunks = splitter.split(sample_text)
    token_counts = [c.token_count for c in chunks]
    over_budget = [t for t in token_counts if t > TOKEN_UPPER_BOUND]

    assert not over_budget, f"token counts: {token_counts}"


# ============================================================
# edge cases（旧脚本 3 个 check → 1 个 parametrize）
# ============================================================

@pytest.mark.parametrize(
    "text, expected_chunks, case",
    [
        ("", 0, "空字符串"),
        ("   \n\n\t  ", 0, "纯空白（strip 后为空）"),
        ("Hello world", 1, "短文本单段落"),
    ],
    ids=["empty", "whitespace-only", "short-text"],
)
def test_split_edge_case_chunk_counts(splitter, text, expected_chunks, case):
    """原 check("empty text") / check("short text")：空输入返回空列表，短输入不分段。"""
    chunks = splitter.split(text)

    assert len(chunks) == expected_chunks, f"{case}: got {len(chunks)} chunks"


def test_split_without_chapter_markers_uses_single_chapter(splitter):
    """原 check("no-chapter fallback")：无「第X章」标记时全文算一个章节。"""
    chunks = splitter.split("段落一。\n\n段落二。\n\n段落三。")
    chapter_indexes = {c.chapter_index for c in chunks}

    assert len(chapter_indexes) == 1, f"chapters: {chapter_indexes}"


# ============================================================
# paragraph mapping（前端原文联动高亮的数据源）
# ============================================================

def test_paragraph_mapping_reports_entries(splitter, sample_text):
    """原 check("has mappings")：反向映射非空，前端才能做段落高亮。"""
    chunks = splitter.split(sample_text)
    mapping = splitter.reconstruct_paragraph_mapping(chunks)

    assert len(mapping) > 0, "paragraph mapping is empty"


def test_paragraph_mapping_covers_leading_paragraphs(splitter, sample_text):
    """原 check("first 5 paragraphs covered")：开头段落必须都有归属 chunk。"""
    chunks = splitter.split(sample_text)
    mapping = splitter.reconstruct_paragraph_mapping(chunks)
    missing = [i for i in range(min(5, len(mapping))) if i not in mapping]

    assert not missing, f"paragraphs without chunk: {missing}"
