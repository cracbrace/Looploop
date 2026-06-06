"""
Pipeline 编排器 — v0.45 单次调用架构

串联文本切分 → 逐段提取 → 角色消歧 → 场景合并 → 最终输出。
v0.45 关键变更：废除 run() + run_with_progress() 双重调用，
改为单一的 async generator `run_pipeline()`，由外部 async for 驱动。
"""

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


@dataclass
class PipelineStage:
    """Pipeline 进度阶段"""
    stage: str
    message: str
    progress: float
    data: dict = field(default_factory=dict)
    logs: list[str] = field(default_factory=list)


@dataclass
class PipelineResult:
    """Pipeline 最终产物"""
    screenplay: Screenplay
    total_elapsed: float


class Pipeline:
    """
    小说→剧本转换 Pipeline — v0.45 单次调用。

    用法：
        pipeline = Pipeline(llm_client)
        result: PipelineResult | None = None
        async for stage in pipeline.run_pipeline(text):
            # 推送 stage 到 SSE
            if stage.stage == "result":
                result = PipelineResult(
                    screenplay=stage.data["screenplay"],
                    total_elapsed=stage.data["elapsed"],
                )
    """

    def __init__(self, llm: LLMClient):
        self.llm = llm
        self.splitter = TextSplitter()
        self.extractor = ChapterExtractor(llm)
        self.resolver = CharacterResolver(llm)
        self.merger = SceneMerger(self.resolver)

    # ============================================================
    # v0.45: 单一 async generator — 进度 + 最终结果合流
    # ============================================================

    async def run_pipeline(
        self,
        text: str,
        meta_overrides: dict | None = None,
    ) -> AsyncIterator[PipelineStage]:
        """
        驱动完整 Pipeline，每个阶段 yield 一个 PipelineStage。

        最后 yield 一个 stage="result" 的 PipelineStage，
        其中 data.screenplay 为完整的 Screenplay 对象。
        """
        t0 = time.time()

        # ── Step 1: 文本切分 ──
        yield PipelineStage(
            stage="splitting",
            message="正在分析文本结构，识别章节与段落...",
            progress=0.05,
        )
        chunks = self.splitter.split(text)
        if not chunks:
            raise ValueError("文本切分后无有效内容。")

        chapter_count = len(set(c.chapter_index for c in chunks))
        yield PipelineStage(
            stage="splitting",
            message=f"文本切分完成，共 {len(chunks)} 段 · {chapter_count} 个章节",
            progress=0.10,
            data={"chunks": len(chunks), "chapters": chapter_count},
            logs=[f"[TextSplitter] 识别到 {chapter_count} 个章节, 切分为 {len(chunks)} 个 Chunk"],
        )

        # ── Step 2-3: 渐进式提取 + 增量角色消歧 ──
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

            pct = 0.15 + 0.50 * (batch_end / total_chunks)
            yield PipelineStage(
                stage="extracting",
                message=f"第 {batch_num}/{total_batches} 批完成 "
                        f"({len(registry)} 个角色已识别)",
                progress=pct,
                data={"completed": batch_end, "total": total_chunks,
                      "characters": len(registry)},
            )

        # ── 后处理去重 (CPU 密集 → 线程池) ──
        yield PipelineStage(
            stage="dedup",
            message="正在全局角色去重...",
            progress=0.70,
        )
        registry, dedup_logs = await asyncio.to_thread(
            _run_dedup_sync, self.resolver, registry, text
        )
        for log_msg in dedup_logs:
            yield PipelineStage(
                stage="character_update",
                message=log_msg,
                progress=0.72,
                data={"log": log_msg, "characters": len(registry)},
                logs=[log_msg],
            )

        yield PipelineStage(
            stage="characters_refine",
            message=f"角色消歧完成，共 {len(registry)} 个唯一角色",
            progress=0.75,
            data={"characters": len(registry)},
        )

        # ── 合并 + 组装 ──
        yield PipelineStage(
            stage="merging",
            message="正在合并相邻场景...",
            progress=0.80,
        )
        all_raw_scenes = []
        for _, r in ordered_results:
            if r:
                all_raw_scenes.extend(r.scenes)

        scenes = self.merger.merge(all_raw_scenes, registry)
        yield PipelineStage(
            stage="merging",
            message=f"场景合并完成，共 {len(scenes)} 个场景",
            progress=0.85,
            data={"scenes": len(scenes)},
        )

        yield PipelineStage(
            stage="building",
            message="正在组装最终剧本...",
            progress=0.95,
        )
        screenplay = self.merger.build_screenplay(
            scenes, registry, meta_overrides
        )
        elapsed = time.time() - t0

        # ── 最终阶段: 包含完整 Screenplay ──
        yield PipelineStage(
            stage="result",
            message=(
                f"转换完成！{screenplay.meta.total_scenes} 场景 · "
                f"{screenplay.meta.total_shots} 镜头 · "
                f"{len(screenplay.characters)} 角色 · "
                f"耗时 {elapsed:.0f}s"
            ),
            progress=1.0,
            data={
                "screenplay": screenplay,
                "scenes": screenplay.meta.total_scenes,
                "shots": screenplay.meta.total_shots,
                "characters": len(screenplay.characters),
                "duration": screenplay.meta.total_duration_estimate,
                "elapsed_seconds": round(elapsed, 1),
            },
        )


def _run_dedup_sync(resolver, registry: dict, text: str) -> tuple[dict, list[str]]:
    """同步包装 deduplicate，供 asyncio.to_thread 使用"""
    import asyncio as _asyncio
    try:
        loop = _asyncio.get_running_loop()
    except RuntimeError:
        loop = None
    if loop is not None and loop.is_running():
        # 在运行中的事件循环里创建新的事件循环给线程
        new_loop = _asyncio.new_event_loop()
        _asyncio.set_event_loop(new_loop)
        try:
            return new_loop.run_until_complete(resolver.deduplicate(registry, text))
        finally:
            new_loop.close()
    else:
        return _asyncio.run(resolver.deduplicate(registry, text))
