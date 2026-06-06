"""
Looploop API 路由

REST API 端点：文本转换、进度流、剧本查询、导出、单镜头重刷、历史管理。
v0.2: 后端存储从内存 dict 迁移到 SQLite。
"""

import asyncio
import json
import uuid
from typing import Optional

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse, Response
from pydantic import BaseModel, Field

from backend.config import settings
from backend.llm_client import LLMClient
from backend.engine.pipeline import Pipeline
from backend.safe_parser import SafeParser
from backend.database import (
    create_task,
    get_task,
    update_task,
    list_tasks,
    delete_task,
    save_screenplay,
)

router = APIRouter(prefix="/api")

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


class ScreenplayUpdate(BaseModel):
    screenplay: dict = Field(..., description="编辑后的完整剧本")


# ============================================================
# 路由
# ============================================================

@router.get("/health")
async def health_check():
    return {
        "status": "ok",
        "app": settings.app_name,
        "version": settings.app_version,
        "llm_model": settings.llm_model,
    }


@router.post("/convert")
async def convert_novel(request: ConvertRequest):
    """提交小说文本，触发转换。返回 task_id。"""
    task_id = uuid.uuid4().hex[:12]
    title = request.title or "Untitled"

    await create_task(task_id, title, original_text=request.text)
    asyncio.create_task(_run_pipeline(task_id, request))

    return {"task_id": task_id}


@router.get("/convert/{task_id}/stream")
async def stream_progress(task_id: str):
    """SSE 端点——实时推送转换进度。"""
    task = await get_task(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="任务不存在")

    async def event_generator():
        last_progress = -1
        while True:
            task = await get_task(task_id)
            if not task:
                break
            if task["status"] in ("done", "error"):
                break
            if task["progress"] != last_progress:
                last_progress = task["progress"]
                logs = task.get("data", {}).get("logs", []) if task.get("data") else []
                event = {
                    "stage": task.get("stage", ""),
                    "message": task.get("message", ""),
                    "progress": task["progress"],
                }
                if logs:
                    event["logs"] = logs
                yield f"data: {json.dumps(event, ensure_ascii=False)}\n\n"
            await asyncio.sleep(0.3)

        # 最终事件
        task = await get_task(task_id)
        if task and task["status"] == "done":
            yield f"data: {json.dumps({'stage': 'done', 'message': task.get('message',''), 'progress': 1.0}, ensure_ascii=False)}\n\n"
        elif task and task["status"] == "error":
            yield f"data: {json.dumps({'stage': 'error', 'message': task.get('error','Unknown'), 'progress': task.get('progress',0)}, ensure_ascii=False)}\n\n"

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
    task = await get_task(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="任务不存在")
    if task["status"] == "error":
        raise HTTPException(status_code=500, detail=task.get("error", "转换失败"))
    if task["status"] != "done":
        return {"status": task["status"], "progress": task["progress"]}
    result = task.get("result", {})
    result["_original_text"] = task.get("original_text", "")
    return result


@router.get("/screenplay/{task_id}/export/yaml")
async def export_yaml(task_id: str):
    """导出 YAML 文件"""
    task = await get_task(task_id)
    if not task or not task.get("result"):
        raise HTTPException(status_code=404, detail="剧本不存在")

    import yaml
    yaml_str = yaml.dump(
        task["result"], allow_unicode=True, sort_keys=False,
        default_flow_style=False, indent=2,
    )
    return Response(
        content=yaml_str, media_type="application/x-yaml",
        headers={"Content-Disposition": f"attachment; filename=screenplay_{task_id}.yaml"},
    )


@router.get("/screenplay/{task_id}/export/word")
async def export_word(task_id: str):
    """导出 Word 文档"""
    task = await get_task(task_id)
    if not task or not task.get("result"):
        raise HTTPException(status_code=404, detail="剧本不存在")

    from docx import Document
    data = task["result"]
    doc = Document()
    doc.styles["Normal"].font.name = "Microsoft YaHei"

    meta = data.get("meta", {})
    doc.add_heading(meta.get("title", "剧本"), 0)
    doc.add_paragraph(f"原著：{meta.get('source','')}  作者：{meta.get('author','')}")
    doc.add_paragraph(f"类型：{meta.get('genre','')}  总时长：{meta.get('total_duration_estimate','')}")
    doc.add_paragraph("")

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

    for scene in data.get("scenes", []):
        doc.add_heading(f"场景 {scene.get('scene_number','')} · {scene.get('location','')}", level=2)
        doc.add_paragraph(
            f"时间：{scene.get('time_of_day','')}  氛围：{scene.get('atmosphere','')}  时长：{scene.get('duration_estimate','')}"
        )
        for shot in scene.get("shots", []):
            p = doc.add_paragraph()
            p.add_run(f"镜头 {shot.get('shot_number','')}  {shot.get('shot_type','')} · {shot.get('camera_movement','')}  {shot.get('duration','')}").bold = True
            dia = shot.get("dialogue")
            if dia:
                doc.add_paragraph(f"  {dia.get('character','')}（{dia.get('emotion','')}）：「{dia.get('line','')}」")

    import io
    buffer = io.BytesIO()
    doc.save(buffer)
    buffer.seek(0)
    return Response(
        content=buffer.getvalue(),
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        headers={"Content-Disposition": f"attachment; filename=screenplay_{task_id}.docx"},
    )


@router.post("/shots/{scene_id}/{shot_id}/regenerate")
async def regenerate_shot(scene_id: str, shot_id: str, request: RegenerateRequest):
    """单镜头重刷——Human-in-the-Loop"""
    screenplay = request.current_screenplay
    target_shot, target_scene = None, None
    for scene in screenplay.get("scenes", []):
        for shot in scene.get("shots", []):
            if shot.get("shot_id") == shot_id:
                target_shot, target_scene = shot, scene
                break

    if not target_shot:
        raise HTTPException(status_code=404, detail=f"Shot {shot_id} 不存在")

    context_shots = []
    if target_scene:
        all_shots = target_scene.get("shots", [])
        target_idx = next((i for i, s in enumerate(all_shots) if s.get("shot_id") == shot_id), -1)
        if target_idx >= 0:
            context_shots = all_shots[max(0, target_idx - 2):min(len(all_shots), target_idx + 3)]

    prompt = f"""请重新生成以下镜头。

原始镜头数据：
```json
{json.dumps(target_shot, ensure_ascii=False, indent=2)}
```

用户反馈：{request.user_feedback or '请自由发挥，生成更精彩的版本'}

上下文镜头（仅供参考，不要修改）：
```json
{json.dumps(context_shots, ensure_ascii=False, indent=2)}
```

请只输出这个镜头的合法 JSON（字段包含 shot_id, shot_number, shot_type, camera_movement, focus_subject, visual_prompt, dialogue, duration 等）。"""

    parser = get_parser()
    try:
        new_shot = await parser.validate_single_shot(
            await get_llm().generate_json(prompt, temperature=0.5)
        )
        return {"shot": new_shot.model_dump()}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"镜头重刷失败: {e}")


# ============================================================
# v0.2 新增：历史管理 + 编辑保存
# ============================================================

@router.get("/tasks")
async def get_tasks():
    """获取历史转换列表"""
    return await list_tasks()


@router.delete("/tasks/{task_id}")
async def remove_task(task_id: str):
    """删除历史任务"""
    task = await get_task(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="任务不存在")
    await delete_task(task_id)
    return {"ok": True}


@router.patch("/screenplay/{task_id}")
async def update_screenplay(task_id: str, body: ScreenplayUpdate):
    """保存编辑后的剧本"""
    task = await get_task(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="任务不存在")
    await save_screenplay(task_id, body.screenplay)
    return {"ok": True}


# ============================================================
# Pipeline 后台执行
# ============================================================

async def _run_pipeline(task_id: str, request: ConvertRequest):
    """后台执行 Pipeline，通过数据库更新进度"""
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

        await update_task(task_id, status="running")

        async for stage in pipeline.run_with_progress(request.text, meta_overrides):
            await update_task(
                task_id,
                status="running",
                stage=stage.stage,
                message=stage.message,
                progress=stage.progress,
                data=stage.data,
            )

        screenplay = await pipeline.run(request.text, meta_overrides)

        # 回填标题：优先 LLM 生成的标题，其次用户提供的，最后用文本第一行
        final_title = screenplay.meta.title if screenplay.meta.title and screenplay.meta.title != "Untitled" else None
        if not final_title and request.title:
            final_title = request.title
        if not final_title:
            first_line = request.text.strip().split("\n")[0][:60]
            final_title = first_line or "Untitled"

        await update_task(
            task_id,
            title=final_title,
            result=screenplay.model_dump(),
            progress=1.0,
            stage="done",
            message=f"完成！{screenplay.meta.total_scenes}场景 {screenplay.meta.total_shots}镜头",
            status="done",
        )

    except Exception as e:
        await update_task(
            task_id,
            status="error",
            error=str(e),
            message=f"转换失败: {e}",
        )
