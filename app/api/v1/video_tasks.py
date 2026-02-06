"""
Video Task API 路由
"""

import asyncio
from typing import Optional

from fastapi import APIRouter, HTTPException, Query, UploadFile, File
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
import orjson

from app.services.video_task_manager import get_video_task_manager
from app.core.video_tasks import get_task, delete_task
from app.core.exceptions import AppException
from app.services.grok.services.assets import UploadService


router = APIRouter(tags=["Video Tasks"])


class CreateVideoTaskRequest(BaseModel):
    """创建视频任务请求"""

    model: str = Field(..., description="模型名称")
    prompt: str = Field(..., description="视频描述提示词")
    aspect_ratio: Optional[str] = Field(
        "3:2", description="视频比例: 2:3, 3:2, 1:1, 9:16, 16:9"
    )
    video_length: Optional[int] = Field(6, description="视频时长(秒): 6 或 10")
    resolution: Optional[str] = Field("480p", description="视频分辨率: 480p, 720p")
    preset: Optional[str] = Field("normal", description="风格预设: fun, normal, spicy, custom")
    image_url: Optional[str] = Field(None, description="图片URL（用于图片转视频）")


class CreateVideoTaskResponse(BaseModel):
    """创建视频任务响应"""

    status: str
    task_id: str
    message: str


def _sse_event(payload: dict) -> str:
    return f"data: {orjson.dumps(payload).decode()}\n\n"


@router.post(
    "/v1/video/tasks",
    response_model=CreateVideoTaskResponse,
    summary="创建视频生成任务",
    description="提交异步视频生成任务，立即返回任务ID",
)
async def create_video_task(request: CreateVideoTaskRequest):
    """创建视频生成任务"""
    from app.core.logger import logger
    
    logger.info(f"Received video task request: model={request.model}, prompt={request.prompt}, image_url={request.image_url}")
    
    try:
        manager = await get_video_task_manager()
        task_id = await manager.create_video_task(
            model=request.model,
            prompt=request.prompt,
            aspect_ratio=request.aspect_ratio,
            video_length=request.video_length,
            resolution=request.resolution,
            preset=request.preset,
            image_url=request.image_url,
        )
        return CreateVideoTaskResponse(
            status="success",
            task_id=task_id,
            message="视频生成任务已提交",
        )
    except AppException as e:
        logger.error(f"AppException in create_video_task: {e.message}")
        raise HTTPException(status_code=e.status_code, detail=e.message)
    except Exception as e:
        logger.error(f"Exception in create_video_task: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get(
    "/v1/video/tasks/{task_id}",
    summary="查询视频任务状态",
    description="根据任务ID查询视频生成状态和结果",
)
async def get_video_task_status(task_id: str):
    """查询视频任务状态"""
    manager = await get_video_task_manager()
    task_status = await manager.get_task_status(task_id)
    
    if not task_status:
        raise HTTPException(status_code=404, detail="任务不存在")
    
    return task_status


@router.get(
    "/v1/video/tasks/{task_id}/stream",
    summary="流式获取视频任务进度",
    description="通过SSE实时获取视频生成进度",
)
async def stream_video_task(task_id: str):
    """流式获取视频任务进度"""
    task = get_task(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="任务不存在")

    async def event_stream():
        queue = task.attach()
        try:
            yield _sse_event({"type": "snapshot", **task.snapshot()})

            final = task.final_event()
            if final:
                yield _sse_event(final)
                return

            while True:
                try:
                    event = await asyncio.wait_for(queue.get(), timeout=15)
                except asyncio.TimeoutError:
                    yield ": ping\n\n"
                    final = task.final_event()
                    if final:
                        yield _sse_event(final)
                        return
                    continue

                yield _sse_event(event)
                if event.get("type") in ("completed", "failed", "cancelled"):
                    return
        finally:
            task.detach(queue)

    return StreamingResponse(event_stream(), media_type="text/event-stream")


@router.delete(
    "/v1/video/tasks/{task_id}",
    summary="取消视频任务",
    description="取消正在进行的视频生成任务",
)
async def cancel_video_task(task_id: str):
    """取消视频任务"""
    manager = await get_video_task_manager()
    success = await manager.cancel_task(task_id)
    
    if not success:
        raise HTTPException(status_code=404, detail="任务不存在")
    
    return {"status": "success", "message": "任务已取消"}


class DeleteTasksRequest(BaseModel):
    """批量删除任务请求"""
    task_ids: list[str] = Field(..., description="任务ID列表")


@router.delete(
    "/v1/video/tasks",
    summary="批量删除视频任务",
    description="批量删除指定的视频任务",
)
async def delete_video_tasks(request: DeleteTasksRequest):
    """批量删除视频任务"""
    from app.core.video_tasks import delete_tasks
    
    count = delete_tasks(request.task_ids)
    return {"status": "success", "count": count, "message": f"已删除 {count} 个任务"}


@router.delete(
    "/v1/video/tasks/status/{status}",
    summary="按状态删除视频任务",
    description="删除指定状态的所有视频任务",
)
async def delete_video_tasks_by_status(status: str):
    """按状态删除视频任务"""
    from app.core.video_tasks import TaskStatus, delete_tasks_by_status
    
    try:
        task_status = TaskStatus(status)
    except ValueError:
        raise HTTPException(
            status_code=400,
            detail=f"无效的状态值: {status}，可选值: pending, running, completed, failed, cancelled"
        )
    
    count = delete_tasks_by_status(task_status)
    return {"status": "success", "count": count, "message": f"已删除 {count} 个 {status} 任务"}


@router.delete(
    "/v1/video/tasks/all",
    summary="清除所有视频任务",
    description="清除所有视频任务",
)
async def clear_all_video_tasks():
    """清除所有视频任务"""
    from app.core.video_tasks import clear_all_tasks
    
    count = clear_all_tasks()
    return {"status": "success", "count": count, "message": f"已清除所有 {count} 个任务"}


@router.get(
    "/v1/video/tasks",
    summary="列出所有视频任务",
    description="获取所有视频任务列表，可按状态筛选",
)
async def list_video_tasks(
    status: Optional[str] = Query(None, description="任务状态: pending, running, completed, failed, cancelled")
):
    """列出所有视频任务"""
    from app.core.video_tasks import TaskStatus, list_tasks

    filter_status = None
    if status:
        try:
            filter_status = TaskStatus(status)
        except ValueError:
            raise HTTPException(
                status_code=400,
                detail=f"无效的状态值: {status}，可选值: pending, running, completed, failed, cancelled"
            )

    tasks = list_tasks(status=filter_status)
    return {"tasks": tasks}


@router.post(
    "/v1/video/upload",
    summary="上传图片",
    description="上传图片到 Grok 服务器，用于图片转视频",
)
async def upload_image(file: UploadFile = File(..., description="图片文件")):
    """上传图片"""
    from app.services.token import get_token_manager

    token_mgr = await get_token_manager()
    await token_mgr.reload_if_stale()
    token = None
    from app.services.grok.models.model import ModelService

    for pool_name in ModelService.pool_candidates_for_model("grok-imagine-1.0-video"):
        token = token_mgr.get_token(pool_name)
        if token:
            break

    if not token:
        raise HTTPException(status_code=503, detail="No available tokens")

    upload_service = UploadService()
    try:
        content = await file.read()
        file_input = f"data:{file.content_type};base64,{content.decode('latin1')}"
        file_id, file_uri = await upload_service.upload(file_input, token)
        return {
            "file_id": file_id,
            "file_uri": file_uri,
            "image_url": f"https://assets.grok.com/{file_uri}"
        }
    finally:
        await upload_service.close()


__all__ = ["router"]
