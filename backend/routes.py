"""
Looploop API 路由

REST API 端点：文本转换、进度流、剧本查询、导出、单镜头重刷。
"""

from __future__ import annotations

import asyncio
import json
import uuid
from typing import Optional

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import StreamingResponse, Response
from pydantic import BaseModel, Field

from backend.config import settings
from backend.llm_client import LLMClient
from backend.engine.pipeline import Pipeline
from backend.safe_parser import SafeParser


router = APIRouter(prefix="/api")

# ============================================================
# 全局状态（MVP 用内存存储，生产应换 Redis/DB）
# ============================================================

# 任务状态存储
task_store: dict[str, dict] = {}

# 懒加载单例
_llm: Optional[LLMClient] = None
_pipeline: Optional[Pipeline] = None
_parser: Optional[SafeParser] = None


def get_llm() -> LLMClient:
    global _llm
    if _llm is None:
        _llm = LLMClient()
    return _llm


def get_pipeline() -> Pipeline:
    global _pipeline
    if _pipeline is None:
        _pipeline = Pipeline(get_llm())
    return _pipeline


def get_parser() -> SafeParser:
    global _parser
    if _parser is None:
        _parser = SafeParser(get_llm())
    return _parser


# ============================================================
# 请求/响应模型
# ============================================================

class ConvertRequest(BaseModel):
    text: str = Field(..., min_length=100, description="小说原文，至少 100 字符")
    title: Optional[str] = Field(default=None, description="剧本标题")
    author: Optional[str] = Field(default=None, description="原作者")
    genre: Optional[str] = Field(default=None, description="类型标签")


class RegenerateRequest(BaseModel):
    user_feedback: str = Field(default="", description="用户修改意见")
    current_screenplay: dict = Field(..., description="当前完整剧本")


# ============================================================
# 路由
# ============================================================

@router.get("/health")
async def health_check():
    """健康检查"""
    return {
        "status": "ok",
        "app": settings.app_name,
        "version": settings.app_version,
        "llm_model": settings.llm_model,
    }


@router.post("/convert")
async def convert_novel(request: ConvertRequest):
    """
    提交小说文本，触发转换。

    返回 task_id，前端用此 ID 订阅 SSE 进度流。
    """
    task_id = uuid.uuid4().hex[:12]

    # 初始化任务状态
    task_store[task_id] = {
        "status": "pending",
        "progress": 0.0,
        "message": "任务已创建",
        "result": None,
        "error": None,
    }

    # 后台执行 Pipeline
    asyncio.create_task(_run_pipeline(task_id, request))

    return {"task_id": task_id}


@router.get("/convert/{task_id}/stream")
async def stream_progress(task_id: str):
    """
    SSE 端点——实时推送转换进度。

    前端通过 EventSource 连接，逐阶段接收进度更新。
    """
    if task_id not in task_store:
        raise HTTPException(status_code=404, detail="任务不存在")

    async def event_generator():
        task = task_store[task_id]
        last_progress = -1

        while task["status"] not in ("done", "error"):
            if task["progress"] != last_progress:
                last_progress = task["progress"]
                yield f"data: {json.dumps({'stage': task.get('stage',''), 'message': task['message'], 'progress': task['progress'], 'data': task.get('data',{})}, ensure_ascii=False)}\n\n"
            await asyncio.sleep(0.3)

        # 最终事件
        if task["status"] == "done":
            yield f"data: {json.dumps({'stage': 'done', 'message': task['message'], 'progress': 1.0, 'data': task.get('data',{})}, ensure_ascii=False)}\n\n"
        else:
            yield f"data: {json.dumps({'stage': 'error', 'message': task.get('error','Unknown error'), 'progress': task['progress']}, ensure_ascii=False)}\n\n"

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.get("/screenplay/{task_id}")
async def get_screenplay(task_id: str):
    """获取最终剧本 JSON"""
    task = task_store.get(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="任务不存在")
    if task["status"] == "error":
        raise HTTPException(status_code=500, detail=task.get("error", "转换失败"))
    if task["status"] != "done":
        return {"status": task["status"], "progress": task["progress"]}

    return task["result"]


@router.get("/screenplay/{task_id}/export/yaml")
async def export_yaml(task_id: str):
    """导出 YAML 文件"""
    task = task_store.get(task_id)
    if not task or not task.get("result"):
        raise HTTPException(status_code=404, detail="剧本不存在")

    screenplay_data = task["result"]
    import yaml
    yaml_str = yaml.dump(
        screenplay_data,
        allow_unicode=True,
        sort_keys=False,
        default_flow_style=False,
        indent=2,
    )
    return Response(
        content=yaml_str,
        media_type="application/x-yaml",
        headers={
            "Content-Disposition": f"attachment; filename=screenplay_{task_id}.yaml"
        },
    )


@router.get("/screenplay/{task_id}/export/word")
async def export_word(task_id: str):
    """导出 Word 文档"""
    task = task_store.get(task_id)
    if not task or not task.get("result"):
        raise HTTPException(status_code=404, detail="剧本不存在")

    from docx import Document

    data = task["result"]
    doc = Document()
    doc.styles["Normal"].font.name = "Microsoft YaHei"

    # 标题
    meta = data.get("meta", {})
    doc.add_heading(meta.get("title", "剧本"), 0)
    doc.add_paragraph(f"原著：{meta.get('source', '')}  作者：{meta.get('author', '')}")
    doc.add_paragraph(f"类型：{meta.get('genre', '')}  预估总时长：{meta.get('total_duration_estimate', '')}")
    doc.add_paragraph("")

    # 角色表
    doc.add_heading("角色表", 1)
    table = doc.add_table(rows=1, cols=4)
    for i, text in enumerate(["角色", "类型", "性别", "描述"]):
        table.rows[0].cells[i].text = text
    for char in data.get("characters", []):
        row = table.add_row()
        row.cells[0].text = char.get("canonical_name", "")
        row.cells[1].text = char.get("role_type", "")
        row.cells[2].text = char.get("gender", "")
        row.cells[3].text = char.get("description", "")
    doc.add_paragraph("")

    # 场景
    for scene in data.get("scenes", []):
        doc.add_heading(
            f"场景 {scene.get('scene_number','')} · {scene.get('location','')}",
            level=2,
        )
        doc.add_paragraph(
            f"时间：{scene.get('time_of_day','')}  "
            f"氛围：{scene.get('atmosphere','')}  "
            f"预估时长：{scene.get('duration_estimate','')}"
        )

        for shot in scene.get("shots", []):
            doc.add_paragraph("")
            p = doc.add_paragraph()
            p.add_run(
                f"镜头 {shot.get('shot_number','')}  "
                f"{shot.get('shot_type','')} · {shot.get('camera_movement','')}  "
                f"{shot.get('duration','')}"
            ).bold = True

            dia = shot.get("dialogue")
            if dia:
                doc.add_paragraph(
                    f"  {dia.get('character','')}（{dia.get('emotion','')}）："
                    f"「{dia.get('line','')}」"
                )

    # 保存到内存
    import io
    buffer = io.BytesIO()
    doc.save(buffer)
    buffer.seek(0)

    return Response(
        content=buffer.getvalue(),
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        headers={
            "Content-Disposition": f"attachment; filename=screenplay_{task_id}.docx"
        },
    )


@router.post("/shots/{scene_id}/{shot_id}/regenerate")
async def regenerate_shot(
    scene_id: str,
    shot_id: str,
    request: RegenerateRequest,
):
    """
    单镜头重刷——Human-in-the-Loop。

    用户对某个镜头不满意，输入修改意见，后端仅重生成该镜头。
    """
    screenplay = request.current_screenplay

    # 找到目标 shot
    target_shot = None
    target_scene = None
    for scene in screenplay.get("scenes", []):
        for shot in scene.get("shots", []):
            if shot.get("shot_id") == shot_id:
                target_shot = shot
                target_scene = scene
                break

    if not target_shot:
        raise HTTPException(status_code=404, detail=f"Shot {shot_id} 不存在")

    # 获取前后上下文（各 2 个镜头）
    context_shots = []
    if target_scene:
        all_shots = target_scene.get("shots", [])
        target_idx = next(
            (i for i, s in enumerate(all_shots) if s.get("shot_id") == shot_id),
            -1,
        )
        if target_idx >= 0:
            start = max(0, target_idx - 2)
            end = min(len(all_shots), target_idx + 3)
            context_shots = all_shots[start:end]

    # 构建 prompt
    prompt = f"""请重新生成以下镜头。

原始镜头数据：
```json
{json.dumps(target_shot, ensure_ascii=False, indent=2)}
```

用户反馈：{request.user_feedback or '请自由发挥，生成更精彩的版本'}

上下文（前后镜头，仅供参考，不要修改）：
```json
{json.dumps(context_shots, ensure_ascii=False, indent=2)}
```

请只输出这个镜头的合法 JSON（字段包含 shot_id, shot_number, shot_type, camera_movement, focus_subject, visual_prompt, dialogue, duration 等）。
"""

    parser = get_parser()
    try:
        # 用 validate_single_shot 轻量校验
        new_shot = await parser.validate_single_shot(
            await get_llm().generate_json(prompt, temperature=0.5)
        )
        return {"shot": new_shot.model_dump()}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"镜头重刷失败: {e}")


# ============================================================
# 内部方法
# ============================================================

async def _run_pipeline(task_id: str, request: ConvertRequest):
    """后台执行 Pipeline，更新 task_store"""
    task = task_store[task_id]

    try:
        pipeline = get_pipeline()
        meta_overrides = {}
        if request.title:
            meta_overrides["title"] = request.title
            meta_overrides["source"] = request.title
        if request.author:
            meta_overrides["author"] = request.author
        if request.genre:
            meta_overrides["genre"] = request.genre

        task["status"] = "running"

        async for stage in pipeline.run_with_progress(
            request.text, meta_overrides
        ):
            task["stage"] = stage.stage
            task["message"] = stage.message
            task["progress"] = stage.progress
            task["data"] = stage.data

        # 获取最终结果（必须在设置 status="done" 之前，避免前端竞态）
        screenplay = await pipeline.run(request.text, meta_overrides)
        task["result"] = screenplay.model_dump()
        task["progress"] = 1.0
        task["stage"] = "done"
        task["status"] = "done"

    except Exception as e:
        task["status"] = "error"
        task["error"] = str(e)
        task["message"] = f"转换失败: {e}"
