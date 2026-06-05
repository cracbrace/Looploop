"""
文本切分模块

将长篇小说文本切分为可独立送入 LLM 的小段。
- 滑动窗口：相邻段 20% 重叠，避免上下文断裂
- 章节约识：优先按章节边界切分
- Token 预算：每段不超过 1500 token
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from backend.config import settings


# ============================================================
# 数据结构
# ============================================================

@dataclass
class Chunk:
    """切分后的文本段"""

    chunk_id: str          # 唯一 ID，如"chunk_000"
    text: str              # 本段文本内容
    chapter_index: int     # 所属章节索引（0-based）
    paragraph_start: int   # 原文段落起始索引（0-based）
    paragraph_end: int     # 原文段落结束索引（开区间）
    token_count: int       # token 估算数


@dataclass
class Chapter:
    """识别到的章节"""

    index: int             # 章节索引
    title: str             # 章节标题
    paragraphs: list[str]  # 段落列表
    start_paragraph: int   # 全局段落起始索引


# ============================================================
# 切分器
# ============================================================

class TextSplitter:
    """
    小说文本切分器。

    策略：
    1. 先识别章节边界（"第X章"、"Chapter X"、分隔符）
    2. 每个章节内部按段落切分
    3. 对超长段落进一步按句子切分
    4. 组装 Chunk 时保证滑动窗口重叠
    """

    # 章节匹配模式
    CHAPTER_PATTERNS = [
        re.compile(r"^第[一二三四五六七八九十百千\d]+章\b", re.MULTILINE),
        re.compile(r"^Chapter\s+\d+", re.MULTILINE | re.IGNORECASE),
        re.compile(r"^第[一二三四五六七八九十百千\d]+回\b", re.MULTILINE),
        re.compile(r"^第[一二三四五六七八九十百千\d]+节\b", re.MULTILINE),
    ]

    # 句子分隔符（中英文）
    SENTENCE_DELIMITERS = re.compile(
        r'(?<=[。！？!?；;…\n"])\s*'
    )

    def __init__(
        self,
        max_tokens: int | None = None,
        overlap_ratio: float | None = None,
    ):
        self.max_tokens = max_tokens or settings.chunk_max_tokens
        self.overlap_ratio = overlap_ratio or settings.chunk_overlap_ratio

    # ============================================================
    # 公开接口
    # ============================================================

    def split(self, text: str) -> list[Chunk]:
        """
        将文本切分为 Chunk 列表。

        Args:
            text: 小说全文

        Returns:
            Chunk 列表，可直接送入 extractor
        """
        if not text.strip():
            return []

        # 预处理：统一换行、移除多余空行
        text = self._normalize(text)

        # Step 1: 识别章节
        chapters = self._split_into_chapters(text)

        # Step 2: 逐章节切分为 Chunk
        all_chunks = []
        for chapter in chapters:
            chapter_chunks = self._split_chapter(chapter)
            all_chunks.extend(chapter_chunks)

        # Step 3: 分配 ID
        for i, chunk in enumerate(all_chunks):
            chunk.chunk_id = f"chunk_{i:03d}"

        return all_chunks

    def reconstruct_paragraph_mapping(self, chunks: list[Chunk]) -> dict[int, list[int]]:
        """
        构建"段落到 Chunk"的反向映射。

        Returns:
            {paragraph_index: [chunk_index, chunk_index, ...]}
            一个段落可能被多个 chunk 引用（因为 overlap）
        """
        mapping: dict[int, list[int]] = {}
        for ci, chunk in enumerate(chunks):
            for pi in range(chunk.paragraph_start, chunk.paragraph_end):
                if pi not in mapping:
                    mapping[pi] = []
                mapping[pi].append(ci)
        return mapping

    # ============================================================
    # 内部方法
    # ============================================================

    def _normalize(self, text: str) -> str:
        """统一文本格式"""
        # 统一换行为 \n
        text = text.replace("\r\n", "\n").replace("\r", "\n")
        # 合并 3 个以上连续空行为 2 个
        text = re.sub(r"\n{3,}", "\n\n", text)
        return text.strip()

    def _split_into_chapters(self, text: str) -> list[Chapter]:
        """
        识别章节边界并拆分。

        若未识别到章节标记，则将全文作为一个章节处理。
        """
        # 尝试用章节模式切割
        lines = text.split("\n")
        chapter_starts: list[tuple[int, str]] = []  # [(line_index, title)]

        for i, line in enumerate(lines):
            stripped = line.strip()
            if not stripped:
                continue
            for pattern in self.CHAPTER_PATTERNS:
                if pattern.match(stripped):
                    chapter_starts.append((i, stripped))
                    break

        if not chapter_starts:
            # 未识别到章节 → 全文作为一个章节
            paragraphs = [p for p in self._split_paragraphs(text) if p.strip()]
            return [Chapter(
                index=0, title="正文",
                paragraphs=paragraphs,
                start_paragraph=0,
            )]

        # 按章节拆分
        chapters = []
        for ci in range(len(chapter_starts)):
            start_line, title = chapter_starts[ci]
            if ci + 1 < len(chapter_starts):
                end_line = chapter_starts[ci + 1][0]
            else:
                end_line = len(lines)

            chapter_lines = lines[start_line:end_line]
            chapter_text = "\n".join(chapter_lines)
            paragraphs = [p for p in self._split_paragraphs(chapter_text) if p.strip()]

            # 计算全局段落起始索引
            global_start = 0
            for prev_chapter in chapters:
                global_start += len(prev_chapter.paragraphs)

            chapters.append(Chapter(
                index=ci,
                title=title,
                paragraphs=paragraphs,
                start_paragraph=global_start,
            ))

        return chapters

    def _split_chapter(self, chapter: Chapter) -> list[Chunk]:
        """
        将一个章节切分为若干 Chunk。

        使用贪心策略：尽可能填满每个 Chunk（不超过 max_tokens），
        下一个 Chunk 从上一个 Chunk 的末尾 20% 处开始（滑动窗口）。
        """
        paragraphs = chapter.paragraphs
        if not paragraphs:
            return []

        chunks = []
        para_idx = 0  # 当前段落指针（章节内相对索引）
        overlap_paragraphs = int(
            len(paragraphs) * self.overlap_ratio * 0.5
        )  # 粗略：重叠 2-3 段

        while para_idx < len(paragraphs):
            chunk_text_parts = []
            current_tokens = 0
            start_para = chapter.start_paragraph + para_idx
            end_para = start_para

            # 贪心填充
            for offset in range(len(paragraphs) - para_idx):
                p = paragraphs[para_idx + offset]
                p_tokens = self._estimate_tokens(p)

                if current_tokens + p_tokens > self.max_tokens and chunk_text_parts:
                    # 当前 Chunk 已满
                    break

                chunk_text_parts.append(p)
                current_tokens += p_tokens
                end_para = chapter.start_paragraph + para_idx + offset + 1

            if not chunk_text_parts:
                # 单段落就超出 max_tokens → 强制切分该段落
                p = paragraphs[para_idx]
                sentences = self._split_sentences(p)
                chunk_text_parts = []
                current_tokens = 0
                for sent in sentences:
                    st = self._estimate_tokens(sent)
                    if current_tokens + st > self.max_tokens and chunk_text_parts:
                        break
                    chunk_text_parts.append(sent)
                    current_tokens += st
                end_para = chapter.start_paragraph + para_idx + 1

            chunk_text = "\n\n".join(chunk_text_parts)
            chunks.append(Chunk(
                chunk_id="",  # 后面统一分配
                text=chunk_text,
                chapter_index=chapter.index,
                paragraph_start=start_para,
                paragraph_end=end_para,
                token_count=self._estimate_tokens(chunk_text),
            ))

            # 移动指针：从上一个 Chunk 的末尾回退 overlap_paragraphs 段
            consumed_paragraphs = end_para - start_para
            if consumed_paragraphs <= overlap_paragraphs:
                para_idx += max(1, consumed_paragraphs)
            else:
                para_idx += consumed_paragraphs - overlap_paragraphs

            # 防止死循环
            if end_para >= chapter.start_paragraph + len(paragraphs):
                break

        return chunks

    @staticmethod
    def _split_paragraphs(text: str) -> list[str]:
        """按段落切分"""
        return text.split("\n\n")

    @staticmethod
    def _split_sentences(text: str) -> list[str]:
        """按句子切分（粗粒度）"""
        parts = TextSplitter.SENTENCE_DELIMITERS.split(text)
        # 合并过短的片段
        merged = []
        buffer = ""
        for part in parts:
            buffer += part
            if len(buffer) >= 10:
                merged.append(buffer)
                buffer = ""
        if buffer:
            if merged:
                merged[-1] += buffer
            else:
                merged.append(buffer)
        return merged if merged else [text]

    @staticmethod
    def _estimate_tokens(text: str) -> int:
        """用 tiktoken 精准计算 token 数"""
        try:
            import tiktoken
            enc = tiktoken.get_encoding("cl100k_base")
            return len(enc.encode(text))
        except Exception:
            return max(1, int(len(text) / 1.5))
