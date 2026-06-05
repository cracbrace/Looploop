"""
Pipeline 编排器

串联文本切分 → 逐段提取 → 角色消歧 → 场景合并 → 最终输出的完整流程。
提供一次性执行和流式进度推送两种模式。
"""

from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass, field
from typing import AsyncIterator, Optional

from backend.config import settings
from backend.llm_client import LLMClient
from backend.models import Screenplay
from backend.engine.text_splitter import TextSplitter
from backend.engine.extractor import ChapterExtractor, ExtractionResult
from backend.engine.character_resolver import CharacterResolver
from backend.engine.scene_merger import SceneMerger


# ============================================================
# 进度数据结构
# ============================================================

@dataclass
class PipelineStage:
    """Pipeline 进度阶段"""
    stage: str           # 阶段标识
    message: str         # 用户可读的消息
    progress: float      # 0.0 ~ 1.0
    data: dict = field(default_factory=dict)


# ============================================================
# Pipeline
# ============================================================

class Pipeline:
    """
    小说→剧本转换 Pipeline。

    使用方式：
        pipeline = Pipeline(llm_client)
        screenplay = await pipeline.run(novel_text)

        # 或流式进度
        async for stage in pipeline.run_with_progress(novel_text):
            print(f"{stage.progress:.0%} {stage.message}")
    """

    def __init__(self, llm: LLMClient):
        self.llm = llm
        self.splitter = TextSplitter()
        self.extractor = ChapterExtractor(llm)
        self.resolver = CharacterResolver(llm)
        self.merger = SceneMerger(self.resolver)

    # ============================================================
    # 一次性执行
    # ============================================================

    async def run(
        self,
        text: str,
        meta_overrides: dict | None = None,
    ) -> Screenplay:
        """
        执行完整转换 Pipeline。

        Args:
            text: 小说全文（3 章以上）
            meta_overrides: Meta 字段覆盖（title、author 等）

        Returns:
            完整的 Screenplay 对象
        """
        t0 = time.time()

        # Step 1: 文本切分
        chunks = self.splitter.split(text)
        if not chunks:
            raise ValueError("文本切分后无有效内容，请检查输入文本长度。")

        # Step 2: 第一遍角色提取（全文扫描）
        first_pass_fragments = "\n\n".join(
            c.text[:500] for c in chunks[:3]  # 取前 3 段做角色初筛
        )
        initial_registry = await self.resolver.resolve(first_pass_fragments)

        # Step 3: 并发逐段提取
        async def extract_chunk(chunk):
            return await self.extractor.extract(
                chunk_text=chunk.text,
                chunk_id=chunk.chunk_id,
                chapter_index=chunk.chapter_index,
                character_registry=initial_registry,
            )

        extraction_results: list[ExtractionResult] = await asyncio.gather(
            *[extract_chunk(c) for c in chunks]
        )

        # 收集所有发现的角色名
        all_found_characters = []
        for result in extraction_results:
            if result:
                all_found_characters.extend(result.characters_found)

        # Step 4: 精化角色消歧
        refined_registry = await self.resolver.resolve(
            text,
            characters_found=all_found_characters,
        )

        # Step 5: 收集所有 RawScene
        all_raw_scenes = []
        for result in extraction_results:
            if result:
                all_raw_scenes.extend(result.scenes)

        # Step 6: 场景合并
        scenes = self.merger.merge(all_raw_scenes, refined_registry)

        # Step 7: 组装最终 Screenplay
        screenplay = self.merger.build_screenplay(
            scenes, refined_registry, meta_overrides
        )

        elapsed = time.time() - t0
        print(f"[Pipeline] Conversion complete in {elapsed:.1f}s: "
              f"{screenplay.meta.total_scenes} scenes, "
              f"{screenplay.meta.total_shots} shots, "
              f"{len(screenplay.characters)} characters")

        return screenplay

    # ============================================================
    # 流式进度推送
    # ============================================================

    async def run_with_progress(
        self,
        text: str,
        meta_overrides: dict | None = None,
    ) -> AsyncIterator[PipelineStage]:
        """
        流式执行 Pipeline，每个阶段 yield 进度信息。

        用于 SSE（Server-Sent Events）推送给前端。
        """
        t0 = time.time()

        # Step 1: 文本切分
        yield PipelineStage(
            stage="splitting",
            message="正在分析文本结构，识别章节与段落...",
            progress=0.05,
        )
        chunks = self.splitter.split(text)
        if not chunks:
            raise ValueError("文本切分后无有效内容。")
        yield PipelineStage(
            stage="splitting",
            message=f"文本切分完成，共 {len(chunks)} 段",
            progress=0.10,
            data={"chunks": len(chunks)},
        )

        # Step 2: 角色初筛
        yield PipelineStage(
            stage="characters_pass1",
            message="正在扫描全文，识别角色...",
            progress=0.15,
        )
        first_pass_text = "\n\n".join(c.text[:500] for c in chunks[:3])
        initial_registry = await self.resolver.resolve(first_pass_text)
        yield PipelineStage(
            stage="characters_pass1",
            message=f"角色初筛完成，发现 {len(initial_registry)} 个角色",
            progress=0.25,
            data={"characters": len(initial_registry)},
        )

        # Step 3: 逐段提取（并发 + 进度回报）
        yield PipelineStage(
            stage="extracting",
            message=f"正在逐段提取场景和镜头（共 {len(chunks)} 段）...",
            progress=0.30,
        )

        async def extract_with_tracking(chunk, index: int):
            result = await self.extractor.extract(
                chunk_text=chunk.text,
                chunk_id=chunk.chunk_id,
                chapter_index=chunk.chapter_index,
                character_registry=initial_registry,
            )
            return (index, result)

        # 并发执行，但通过 gather 等待全部完成
        tasks = [extract_with_tracking(c, i) for i, c in enumerate(chunks)]
        extraction_results: list[ExtractionResult] = []
        completed = 0
        for coro in asyncio.as_completed(tasks):
            idx, result = await coro
            extraction_results.append((idx, result))
            completed += 1
            progress = 0.30 + 0.30 * (completed / len(chunks))
            yield PipelineStage(
                stage="extracting",
                message=f"正在提取场景和镜头... {completed}/{len(chunks)}",
                progress=progress,
                data={"completed": completed, "total": len(chunks)},
            )

        # 按原始顺序排序
        extraction_results.sort(key=lambda x: x[0])
        ordered_results = [r for _, r in extraction_results]

        # 收集角色
        all_found = []
        for r in ordered_results:
            if r:
                all_found.extend(r.characters_found)

        # Step 4: 精化角色消歧
        yield PipelineStage(
            stage="characters_refine",
            message="正在合并角色别名，构建全局角色字典...",
            progress=0.65,
        )
        refined_registry = await self.resolver.resolve(
            text, characters_found=all_found
        )
        yield PipelineStage(
            stage="characters_refine",
            message=f"角色消歧完成，共 {len(refined_registry)} 个唯一角色",
            progress=0.75,
            data={"characters": len(refined_registry)},
        )

        # Step 5: 收集 + 合并
        yield PipelineStage(
            stage="merging",
            message="正在合并相邻场景...",
            progress=0.80,
        )
        all_raw_scenes = []
        for r in ordered_results:
            if r:
                all_raw_scenes.extend(r.scenes)

        scenes = self.merger.merge(all_raw_scenes, refined_registry)
        yield PipelineStage(
            stage="merging",
            message=f"场景合并完成，共 {len(scenes)} 个场景",
            progress=0.85,
            data={"scenes": len(scenes)},
        )

        # Step 6: 组装
        yield PipelineStage(
            stage="building",
            message="正在组装最终剧本...",
            progress=0.90,
        )
        screenplay = self.merger.build_screenplay(
            scenes, refined_registry, meta_overrides
        )

        elapsed = time.time() - t0
        yield PipelineStage(
            stage="done",
            message=(
                f"转换完成！{screenplay.meta.total_scenes} 场景 · "
                f"{screenplay.meta.total_shots} 镜头 · "
                f"{len(screenplay.characters)} 角色 · "
                f"耗时 {elapsed:.0f}s"
            ),
            progress=1.0,
            data={
                "scenes": screenplay.meta.total_scenes,
                "shots": screenplay.meta.total_shots,
                "characters": len(screenplay.characters),
                "duration": screenplay.meta.total_duration_estimate,
                "elapsed_seconds": round(elapsed, 1),
            },
        )
