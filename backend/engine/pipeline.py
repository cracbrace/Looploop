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
    logs: list[str] = field(default_factory=list)  # v0.3: 结构化日志


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

        # Step 2-3: 渐进式提取 + 增量角色消歧
        BATCH_SIZE = 3
        registry: dict = {}
        all_raw_scenes = []

        for batch_start in range(0, len(chunks), BATCH_SIZE):
            batch_end = min(batch_start + BATCH_SIZE, len(chunks))
            batch = chunks[batch_start:batch_end]

            # 并发提取本批次
            async def extract_one(chunk):
                return await self.extractor.extract(
                    chunk_text=chunk.text, chunk_id=chunk.chunk_id,
                    chapter_index=chunk.chapter_index,
                    character_registry=registry if registry else None,
                    paragraph_offset=chunk.paragraph_start,
                )
            batch_results = await asyncio.gather(*[extract_one(c) for c in batch])

            # 收集 RawScene + 新角色
            batch_characters = []
            for r in batch_results:
                if r:
                    all_raw_scenes.extend(r.scenes)
                    batch_characters.extend(r.characters_found)

            # 增量消歧
            if batch_characters:
                batch_text = " ".join(c.text[:300] for c in batch)
                registry, _ = await self.resolver.resolve_incremental(
                    registry, batch_characters, batch_text
                )

        # 后处理去重：跨 Chunk 批次归并同名/同人角色
        registry, _ = await self.resolver.deduplicate(registry, text)

        # Step 4: 场景合并
        scenes = self.merger.merge(all_raw_scenes, registry)

        # Step 5: 组装最终 Screenplay
        screenplay = self.merger.build_screenplay(
            scenes, registry, meta_overrides
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
            logs=[f"[TextSplitter] 识别到 {len(set(c.chapter_index for c in chunks))} 个章节, 切分为 {len(chunks)} 个 Chunk"],
        )

        # Step 2-3: 渐进式提取 + 增量角色消歧
        # 将 chunks 分批，每批 3 个。每批完成后做增量消歧，
        # 更新后的 registry 作为 few-shot 注入下一批。
        BATCH_SIZE = 3
        registry: dict = {}
        ordered_results: list = []
        total_chunks = len(chunks)

        for batch_start in range(0, total_chunks, BATCH_SIZE):
            batch_end = min(batch_start + BATCH_SIZE, total_chunks)
            batch = chunks[batch_start:batch_end]
            batch_num = batch_start // BATCH_SIZE + 1
            total_batches = (total_chunks + BATCH_SIZE - 1) // BATCH_SIZE

            yield PipelineStage(
                stage="extracting",
                message=f"正在提取: 第 {batch_num}/{total_batches} 批 "
                        f"({batch_start+1}-{batch_end}/{total_chunks} 段)...",
                progress=0.15 + 0.50 * (batch_start / total_chunks),
                data={"batch": batch_num, "total_batches": total_batches},
            )

            # 并发提取当前批次
            async def extract_one(chunk, idx: int):
                return idx, await self.extractor.extract(
                    chunk_text=chunk.text,
                    chunk_id=chunk.chunk_id,
                    chapter_index=chunk.chapter_index,
                    character_registry=registry if registry else None,
                    paragraph_offset=chunk.paragraph_start,
                )

            batch_tasks = [extract_one(c, batch_start + i) for i, c in enumerate(batch)]
            batch_results = await asyncio.gather(*batch_tasks)
            batch_results.sort(key=lambda x: x[0])
            ordered_results.extend(batch_results)

            # 收集本批新角色
            batch_characters = []
            for _, result in batch_results:
                if result:
                    batch_characters.extend(result.characters_found)

            # 增量消歧
            if batch_characters:
                batch_text = " ".join(c.text[:300] for c in batch)
                registry, logs = await self.resolver.resolve_incremental(
                    registry, batch_characters, batch_text
                )
                for log_msg in logs:
                    yield PipelineStage(
                        stage="character_update",
                        message=log_msg,
                        progress=0.15 + 0.50 * (batch_end / total_chunks),
                        data={"log": log_msg, "characters": len(registry)},
                        logs=[log_msg],
                    )

            # 进度
            pct = 0.15 + 0.50 * (batch_end / total_chunks)
            yield PipelineStage(
                stage="extracting",
                message=f"第 {batch_num}/{total_batches} 批完成 "
                        f"({len(registry)} 个角色已识别)",
                progress=pct,
                data={"completed": batch_end, "total": total_chunks,
                      "characters": len(registry)},
            )

        # 后处理去重：跨 Chunk 批次归并同名/同人角色
        refined_registry, dedup_logs = await self.resolver.deduplicate(registry, text)
        for log_msg in dedup_logs:
            yield PipelineStage(
                stage="character_update",
                message=log_msg,
                progress=0.72,
                data={"log": log_msg, "characters": len(refined_registry)},
                logs=[log_msg],
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
        for _, r in ordered_results:
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
            progress=0.95,
        )
        screenplay = self.merger.build_screenplay(
            scenes, refined_registry, meta_overrides
        )

        elapsed = time.time() - t0
        # "done" stage is sent by routes._run_pipeline AFTER setting task["result"]
        # to avoid a race condition where the frontend fetches result before it's ready
        yield PipelineStage(
            stage="building",
            message=(
                f"转换完成！{screenplay.meta.total_scenes} 场景 · "
                f"{screenplay.meta.total_shots} 镜头 · "
                f"{len(screenplay.characters)} 角色 · "
                f"耗时 {elapsed:.0f}s"
            ),
            progress=0.99,
            data={
                "scenes": screenplay.meta.total_scenes,
                "shots": screenplay.meta.total_shots,
                "characters": len(screenplay.characters),
                "duration": screenplay.meta.total_duration_estimate,
                "elapsed_seconds": round(elapsed, 1),
            },
        )
