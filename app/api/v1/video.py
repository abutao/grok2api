"""
视频生成异步 API：提交任务、查询进度与结果
"""

import asyncio
from typing import Any, Optional, List, Dict

import orjson
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from app.core.video_jobs import (
    create_video_job,
    get_video_job,
    list_all_video_jobs,
    expire_video_job,
)
from app.core.batch_tasks import create_task, get_task, expire_task
from app.services.grok.utils.batch import run_in_batches
from app.services.grok.models.model import ModelService
from app.core.exceptions import ValidationException
from app.core.logger import logger


router = APIRouter(tags=["Video"])


def _sse_event(payload: dict) -> str:
    return f"data: {orjson.dumps(payload).decode()}\n\n"


class CreateVideoTaskRequest(BaseModel):
    """创建视频任务请求模型"""
    prompt: str = Field(..., description="视频生成提示词")
    aspect_ratio: Optional[str] = Field("9:16", description="视频宽高比")
    resolution: Optional[str] = Field("480p", description="视频分辨率")
    video_length: Optional[int] = Field(6, description="视频长度（秒）")
    preset: Optional[str] = Field("normal", description="视频预设")
    model: Optional[str] = Field("grok-imagine-1.0-video", description="视频模型")


class VideoTaskResponse(BaseModel):
    """视频任务响应模型"""
    task_id: str
    job_id: str
    status: str
    message: Optional[str] = None


class VideoTaskStatusResponse(BaseModel):
    """视频任务状态响应模型"""
    task_id: str
    job_id: str
    status: str
    progress: int
    result: Optional[Dict[str, Any]] = None
    error: Optional[str] = None
    video_url: Optional[str] = None
    thumbnail_url: Optional[str] = None
    created_at: float
    completed_at: Optional[float] = None


@router.post("/video/generations/async")
async def video_generations_async(request: Request):
    """
    异步提交视频生成任务。
    请求体与 POST /v1/chat/completions 一致（需为视频模型），且建议 stream 不传或为 false。
    立即返回 job_id，后续通过 GET /v1/video/jobs/{job_id} 或 GET /v1/video/jobs/{job_id}/stream 查询进度与结果。
    """
    from app.api.v1.chat import ChatCompletionRequest, VideoConfig, validate_request
    from app.services.grok.services.media import VideoService

    body = await request.json()
    
    # 兼容性处理：将 prompt 格式转换为 messages 格式
    if "prompt" in body and "messages" not in body:
        prompt = body.get("prompt", "")
        aspect_ratio = body.get("aspect_ratio", "9:16")
        resolution = body.get("resolution", "480p")
        video_length = body.get("video_length", 6)
        preset = body.get("preset", "normal")
        
        # 转换为标准格式
        body = {
            "model": body.get("model", "grok-imagine-1.0-video"),
            "messages": [{"role": "user", "content": prompt}],
            "video_config": {
                "aspect_ratio": aspect_ratio,
                "video_length": video_length,
                "resolution_name": resolution,
                "preset": preset
            }
        }
    
    try:
        req = ChatCompletionRequest.model_validate(body)
    except Exception as e:
        raise HTTPException(status_code=422, detail=str(e))

    validate_request(req)
    model_info = ModelService.get(req.model)
    if not model_info or not model_info.is_video:
        raise HTTPException(
            status_code=400,
            detail="Only video models (e.g. grok-imagine-1.0-video) are supported for async video generation",
        )

    v_conf = req.video_config or VideoConfig()
    job = create_video_job()
    job.request_payload = {
        "model": req.model,
        "messages": [{"role": m.role, "content": m.content if isinstance(m.content, str) else "[multimodal]"} for m in req.messages],
        "video_config": {"aspect_ratio": v_conf.aspect_ratio, "video_length": v_conf.video_length, "resolution_name": v_conf.resolution_name, "preset": v_conf.preset},
    }

    def progress_callback(progress: int, result: Optional[dict] = None) -> None:
        if result is not None:
            # 处理结果，确保视频链接正确提取
            if isinstance(result, dict):
                # 支持多种视频链接格式
                video_url = None
                thumbnail_url = None
                
                # 情况1：result 直接包含 video_url
                if "video_url" in result:
                    video_url = result["video_url"]
                    thumbnail_url = result.get("thumbnail_url", "")
                # 情况2：result.choices[0].message.content 格式
                elif "choices" in result:
                    choices = result.get("choices", [])
                    if choices and len(choices) > 0:
                        message = choices[0].get("message", {})
                        content = message.get("content", "")
                        
                        # 如果内容是HTML格式，提取视频URL
                        if "<video" in content and "src=" in content:
                            import re
                            match = re.search(r'src="([^"]+)"', content)
                            if match:
                                video_url = match.group(1)
                                # 尝试提取缩略图URL
                                poster_match = re.search(r'poster="([^"]+)"', content)
                                if poster_match:
                                    thumbnail_url = poster_match.group(1)
                        # 如果内容是纯URL
                        elif content.startswith("http"):
                            video_url = content
                # 情况3：result 直接包含 content
                elif "content" in result:
                    content = result.get("content", "")
                    if content.startswith("http"):
                        video_url = content
                
                # 如果找到了视频链接，确保结果中包含
                if video_url:
                    result["video_url"] = video_url
                    if thumbnail_url:
                        result["thumbnail_url"] = thumbnail_url
            
            job.finish(result)
        else:
            job.set_running(progress) if job.status == "pending" else job.set_progress(progress)

    async def run_video() -> None:
        job.set_running(0)
        try:
            stream = await VideoService.completions(
                model=req.model,
                messages=[m.model_dump() for m in req.messages],
                stream=True,
                thinking=req.thinking,
                aspect_ratio=v_conf.aspect_ratio,
                video_length=v_conf.video_length,
                resolution=v_conf.resolution_name,
                preset=v_conf.preset,
                progress_callback=progress_callback,
            )
            async for _ in stream:
                pass
            if job.status == "running":
                job.fail("Stream ended without result")
        except Exception as e:
            logger.exception("Video async job failed: %s", e)
            msg = str(e)
            if "429" in msg:
                msg = "上游限流(429)，请稍后重试"
            job.fail(msg)
        finally:
            asyncio.create_task(expire_video_job(job.id, 3600))

    asyncio.create_task(run_video())
    return {
        "job_id": job.id,
        "status": "pending",
        "message": "Video generation started. Poll GET /v1/video/jobs/{job_id} or connect to GET /v1/video/jobs/{job_id}/stream for progress.",
    }


@router.get("/video/jobs/{job_id}")
async def get_video_job_status(job_id: str):
    """轮询查询视频任务状态与结果。"""
    job = get_video_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    
    out = job.snapshot()
    
    # 提取视频URL（兼容多种格式）
    if job.result and job.status == "completed":
        # 情况1：result 直接包含 video_url
        if "video_url" in job.result:
            out["video_url"] = job.result["video_url"]
            out["thumbnail_url"] = job.result.get("thumbnail_url", "")
        # 情况2：result.choices[0].message.content 格式
        elif "choices" in job.result:
            choices = job.result.get("choices", [])
            if choices and len(choices) > 0:
                message = choices[0].get("message", {})
                content = message.get("content", "")
                
                # 如果内容是HTML格式，提取视频URL
                if "<video" in content and "src=" in content:
                    import re
                    match = re.search(r'src="([^"]+)"', content)
                    if match:
                        out["video_url"] = match.group(1)
                        out["thumbnail_url"] = ""
                        # 尝试提取缩略图URL
                        poster_match = re.search(r'poster="([^"]+)"', content)
                        if poster_match:
                            out["thumbnail_url"] = poster_match.group(1)
                # 如果内容是纯URL
                elif content.startswith("http"):
                    out["video_url"] = content
                    out["thumbnail_url"] = ""
        # 情况3：result 直接包含 content
        elif "content" in job.result:
            content = job.result.get("content", "")
            if content.startswith("http"):
                out["video_url"] = content
                out["thumbnail_url"] = ""
    
    return out


@router.get("/video/jobs/{job_id}/stream")
async def stream_video_job_progress(job_id: str, request: Request):
    """SSE 流式获取视频任务进度与结果。"""
    job = get_video_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    async def event_stream():
        queue = job.attach()
        try:
            # 发送初始状态，包含视频URL（如果已完成）
            initial_state = job.snapshot()
            if job.result and job.status == "completed":
                # 提取视频URL
                video_url = None
                thumbnail_url = None
                
                # 情况1：result 直接包含 video_url
                if "video_url" in job.result:
                    video_url = job.result["video_url"]
                    thumbnail_url = job.result.get("thumbnail_url", "")
                # 情况2：result.choices[0].message.content 格式
                elif "choices" in job.result:
                    choices = job.result.get("choices", [])
                    if choices and len(choices) > 0:
                        message = choices[0].get("message", {})
                        content = message.get("content", "")
                        
                        # 如果内容是HTML格式，提取视频URL
                        if "<video" in content and "src=" in content:
                            import re
                            match = re.search(r'src="([^"]+)"', content)
                            if match:
                                video_url = match.group(1)
                                # 尝试提取缩略图URL
                                poster_match = re.search(r'poster="([^"]+)"', content)
                                if poster_match:
                                    thumbnail_url = poster_match.group(1)
                        # 如果内容是纯URL
                        elif content.startswith("http"):
                            video_url = content
                # 情况3：result 直接包含 content
                elif "content" in job.result:
                    content = job.result.get("content", "")
                    if content.startswith("http"):
                        video_url = content
                
                if video_url:
                    initial_state["video_url"] = video_url
                    if thumbnail_url:
                        initial_state["thumbnail_url"] = thumbnail_url
            
            yield _sse_event({"type": "snapshot", **initial_state})
            
            if job.status in ("completed", "failed", "cancelled"):
                return
                
            while True:
                try:
                    event = await asyncio.wait_for(queue.get(), timeout=15)
                except asyncio.TimeoutError:
                    yield ": ping\n\n"
                    if job.status in ("completed", "failed", "cancelled"):
                        final_state = job.snapshot()
                        if job.result and job.status == "completed":
                            # 提取视频URL
                            video_url = None
                            thumbnail_url = None
                            
                            # 情况1：result 直接包含 video_url
                            if "video_url" in job.result:
                                video_url = job.result["video_url"]
                                thumbnail_url = job.result.get("thumbnail_url", "")
                            # 情况2：result.choices[0].message.content 格式
                            elif "choices" in job.result:
                                choices = job.result.get("choices", [])
                                if choices and len(choices) > 0:
                                    message = choices[0].get("message", {})
                                    content = message.get("content", "")
                                    
                                    # 如果内容是HTML格式，提取视频URL
                                    if "<video" in content and "src=" in content:
                                        import re
                                        match = re.search(r'src="([^"]+)"', content)
                                        if match:
                                            video_url = match.group(1)
                                            # 尝试提取缩略图URL
                                            poster_match = re.search(r'poster="([^"]+)"', content)
                                            if poster_match:
                                                thumbnail_url = poster_match.group(1)
                                    # 如果内容是纯URL
                                    elif content.startswith("http"):
                                        video_url = content
                            # 情况3：result 直接包含 content
                            elif "content" in job.result:
                                content = job.result.get("content", "")
                                if content.startswith("http"):
                                    video_url = content
                            
                            if video_url:
                                final_state["video_url"] = video_url
                                if thumbnail_url:
                                    final_state["thumbnail_url"] = thumbnail_url
                        yield _sse_event({"type": job.status, **final_state})
                        return
                    continue
                
                # 处理事件，确保包含视频URL（如果已完成）
                if event.get("type") == "completed" and job.result:
                    event_copy = dict(event)
                    # 提取视频URL
                    video_url = None
                    thumbnail_url = None
                    
                    # 情况1：result 直接包含 video_url
                    if "video_url" in job.result:
                        video_url = job.result["video_url"]
                        thumbnail_url = job.result.get("thumbnail_url", "")
                    # 情况2：result.choices[0].message.content 格式
                    elif "choices" in job.result:
                        choices = job.result.get("choices", [])
                        if choices and len(choices) > 0:
                            message = choices[0].get("message", {})
                            content = message.get("content", "")
                            
                            # 如果内容是HTML格式，提取视频URL
                            if "<video" in content and "src=" in content:
                                import re
                                match = re.search(r'src="([^"]+)"', content)
                                if match:
                                    video_url = match.group(1)
                                    # 尝试提取缩略图URL
                                    poster_match = re.search(r'poster="([^"]+)"', content)
                                    if poster_match:
                                        thumbnail_url = poster_match.group(1)
                            # 如果内容是纯URL
                            elif content.startswith("http"):
                                video_url = content
                    # 情况3：result 直接包含 content
                    elif "content" in job.result:
                        content = job.result.get("content", "")
                        if content.startswith("http"):
                            video_url = content
                    
                    if video_url:
                        event_copy["video_url"] = video_url
                        if thumbnail_url:
                            event_copy["thumbnail_url"] = thumbnail_url
                    yield _sse_event(event_copy)
                else:
                    yield _sse_event(event)
                
                if event.get("type") in ("completed", "failed", "cancelled"):
                    return
        finally:
            job.detach(queue)

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "Connection": "keep-alive"},
    )


# ---------- 兼容旧版：/v1/video/tasks 风格（与 /v1/video/jobs、generations/async 等价） ----------


@router.post("/video/tasks")
async def video_tasks_create(request: Request):
    """
    异步提交视频生成任务（与 POST /v1/video/generations/async 等价）。
    响应返回 task_id，与 job_id 同值，用于 GET /v1/video/tasks/{task_id} 或 .../stream。
    """
    res = await video_generations_async(request)
    # 兼容旧客户端：同时返回 task_id（值同 job_id）
    res["task_id"] = res["job_id"]
    return res


@router.get("/video/tasks/{task_id}")
async def get_video_task_status(task_id: str):
    """查询视频任务状态与结果（与 GET /v1/video/jobs/{job_id} 等价）。"""
    job = get_video_job(task_id)
    if not job:
        raise HTTPException(status_code=404, detail="Task not found")
    out = job.snapshot()
    out["task_id"] = out["job_id"]
    
    # 提取视频URL（兼容多种格式）
    if job.result and job.status == "completed":
        # 情况1：result 直接包含 video_url
        if "video_url" in job.result:
            out["video_url"] = job.result["video_url"]
            out["thumbnail_url"] = job.result.get("thumbnail_url", "")
        # 情况2：result.choices[0].message.content 格式
        elif "choices" in job.result:
            choices = job.result.get("choices", [])
            if choices and len(choices) > 0:
                message = choices[0].get("message", {})
                content = message.get("content", "")
                
                # 如果内容是HTML格式，提取视频URL
                if "<video" in content and "src=" in content:
                    import re
                    match = re.search(r'src="([^"]+)"', content)
                    if match:
                        out["video_url"] = match.group(1)
                        out["thumbnail_url"] = ""
                        # 尝试提取缩略图URL
                        poster_match = re.search(r'poster="([^"]+)"', content)
                        if poster_match:
                            out["thumbnail_url"] = poster_match.group(1)
                # 如果内容是纯URL
                elif content.startswith("http"):
                    out["video_url"] = content
                    out["thumbnail_url"] = ""
        # 情况3：result 直接包含 content
        elif "content" in job.result:
            content = job.result.get("content", "")
            if content.startswith("http"):
                out["video_url"] = content
                out["thumbnail_url"] = ""
    
    return out


@router.get("/video/tasks/{task_id}/stream")
async def stream_video_task_progress(task_id: str, request: Request):
    """SSE 流式获取视频任务进度（与 GET /v1/video/jobs/{job_id}/stream 等价）。"""
    job = get_video_job(task_id)
    if not job:
        raise HTTPException(status_code=404, detail="Task not found")

    async def event_stream():
        queue = job.attach()
        try:
            # 发送初始状态
            ev = {"type": "snapshot", **job.snapshot()}
            ev["task_id"] = ev["job_id"]
            
            # 提取视频URL（如果已完成）
            if job.result and job.status == "completed":
                # 情况1：result 直接包含 video_url
                if "video_url" in job.result:
                    ev["video_url"] = job.result["video_url"]
                    ev["thumbnail_url"] = job.result.get("thumbnail_url", "")
                # 情况2：result.choices[0].message.content 格式
                elif "choices" in job.result:
                    choices = job.result.get("choices", [])
                    if choices and len(choices) > 0:
                        message = choices[0].get("message", {})
                        content = message.get("content", "")
                        
                        # 如果内容是HTML格式，提取视频URL
                        if "<video" in content and "src=" in content:
                            import re
                            match = re.search(r'src="([^"]+)"', content)
                            if match:
                                ev["video_url"] = match.group(1)
                                ev["thumbnail_url"] = ""
                                # 尝试提取缩略图URL
                                poster_match = re.search(r'poster="([^"]+)"', content)
                                if poster_match:
                                    ev["thumbnail_url"] = poster_match.group(1)
                        # 如果内容是纯URL
                        elif content.startswith("http"):
                            ev["video_url"] = content
                            ev["thumbnail_url"] = ""
                # 情况3：result 直接包含 content
                elif "content" in job.result:
                    content = job.result.get("content", "")
                    if content.startswith("http"):
                        ev["video_url"] = content
                        ev["thumbnail_url"] = ""
            
            yield _sse_event(ev)
            
            if job.status in ("completed", "failed", "cancelled"):
                return
                
            while True:
                try:
                    event = await asyncio.wait_for(queue.get(), timeout=15)
                except asyncio.TimeoutError:
                    yield ": ping\n\n"
                    if job.status in ("completed", "failed", "cancelled"):
                        ev = {**job.snapshot(), "type": job.status}
                        ev["task_id"] = ev["job_id"]
                        
                        # 提取视频URL（如果已完成）
                        if job.result and job.status == "completed":
                            # 情况1：result 直接包含 video_url
                            if "video_url" in job.result:
                                ev["video_url"] = job.result["video_url"]
                                ev["thumbnail_url"] = job.result.get("thumbnail_url", "")
                            # 情况2：result.choices[0].message.content 格式
                            elif "choices" in job.result:
                                choices = job.result.get("choices", [])
                                if choices and len(choices) > 0:
                                    message = choices[0].get("message", {})
                                    content = message.get("content", "")
                                    
                                    # 如果内容是HTML格式，提取视频URL
                                    if "<video" in content and "src=" in content:
                                        import re
                                        match = re.search(r'src="([^"]+)"', content)
                                        if match:
                                            ev["video_url"] = match.group(1)
                                            ev["thumbnail_url"] = ""
                                            # 尝试提取缩略图URL
                                            poster_match = re.search(r'poster="([^"]+)"', content)
                                            if poster_match:
                                                ev["thumbnail_url"] = poster_match.group(1)
                                    # 如果内容是纯URL
                                    elif content.startswith("http"):
                                        ev["video_url"] = content
                                        ev["thumbnail_url"] = ""
                            # 情况3：result 直接包含 content
                            elif "content" in job.result:
                                content = job.result.get("content", "")
                                if content.startswith("http"):
                                    ev["video_url"] = content
                                    ev["thumbnail_url"] = ""
                        
                        yield _sse_event(ev)
                        return
                    continue
                
                # 处理事件，确保包含 task_id 和视频URL（如果已完成）
                e = dict(event)
                e["task_id"] = e.get("job_id", job.id)
                
                if e.get("type") == "completed" and job.result:
                    # 提取视频URL
                    video_url = None
                    thumbnail_url = None
                    
                    # 情况1：result 直接包含 video_url
                    if "video_url" in job.result:
                        video_url = job.result["video_url"]
                        thumbnail_url = job.result.get("thumbnail_url", "")
                    # 情况2：result.choices[0].message.content 格式
                    elif "choices" in job.result:
                        choices = job.result.get("choices", [])
                        if choices and len(choices) > 0:
                            message = choices[0].get("message", {})
                            content = message.get("content", "")
                            
                            # 如果内容是HTML格式，提取视频URL
                            if "<video" in content and "src=" in content:
                                import re
                                match = re.search(r'src="([^"]+)"', content)
                                if match:
                                    video_url = match.group(1)
                                    # 尝试提取缩略图URL
                                    poster_match = re.search(r'poster="([^"]+)"', content)
                                    if poster_match:
                                        thumbnail_url = poster_match.group(1)
                            # 如果内容是纯URL
                            elif content.startswith("http"):
                                video_url = content
                    # 情况3：result 直接包含 content
                    elif "content" in job.result:
                        content = job.result.get("content", "")
                        if content.startswith("http"):
                            video_url = content
                    
                    if video_url:
                        e["video_url"] = video_url
                        if thumbnail_url:
                            e["thumbnail_url"] = thumbnail_url
                
                yield _sse_event(e)
                if event.get("type") in ("completed", "failed", "cancelled"):
                    return
        finally:
            job.detach(queue)

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "Connection": "keep-alive"},
    )


@router.get("/video/tasks")
async def list_video_tasks():
    """获取所有视频任务列表。"""
    try:
        jobs = list_all_video_jobs()
        tasks = []
        
        for job in jobs:
            task = dict(job)
            task["task_id"] = task["job_id"]
            
            # 提取视频URL（兼容多种格式）
            if task.get("result") and task.get("status") == "completed":
                result = task["result"]
                # 情况1：result 直接包含 video_url
                if "video_url" in result:
                    task["video_url"] = result["video_url"]
                    task["thumbnail_url"] = result.get("thumbnail_url", "")
                # 情况2：result.choices[0].message.content 格式
                elif "choices" in result:
                    choices = result.get("choices", [])
                    if choices and len(choices) > 0:
                        message = choices[0].get("message", {})
                        content = message.get("content", "")
                        
                        # 如果内容是HTML格式，提取视频URL
                        if "<video" in content and "src=" in content:
                            import re
                            match = re.search(r'src="([^"]+)"', content)
                            if match:
                                task["video_url"] = match.group(1)
                                task["thumbnail_url"] = ""
                                # 尝试提取缩略图URL
                                poster_match = re.search(r'poster="([^"]+)"', content)
                                if poster_match:
                                    task["thumbnail_url"] = poster_match.group(1)
                        # 如果内容是纯URL
                        elif content.startswith("http"):
                            task["video_url"] = content
                            task["thumbnail_url"] = ""
                # 情况3：result 直接包含 content
                elif "content" in result:
                    content = result.get("content", "")
                    if content.startswith("http"):
                        task["video_url"] = content
                        task["thumbnail_url"] = ""
            
            tasks.append(task)
        
        return {"tasks": tasks, "total": len(tasks)}
        
    except Exception as e:
        logger.error(f"List video tasks failed: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to list video tasks: {str(e)}")


@router.post("/video/tasks/{task_id}/cancel")
async def cancel_video_task(task_id: str):
    """取消视频任务。"""
    try:
        job = get_video_job(task_id)
        if not job:
            raise HTTPException(status_code=404, detail="Task not found")
        
        # 标记任务为取消
        job.status = "cancelled"
        job.error = "Task cancelled by user"
        job.completed_at = time.time()
        job._broadcast({"type": "cancelled", "job_id": job.id, "status": job.status, "error": job.error})
        
        return {"status": "success", "message": "Video task cancelled"}
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Cancel video task failed: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to cancel video task: {str(e)}")


# ---------- 批量处理接口 ----------


@router.post("/video/tasks/batch")
async def create_batch_video_tasks(
    requests: List[CreateVideoTaskRequest],
):
    """
    批量创建视频生成任务
    """
    try:
        # 输入验证
        if not requests:
            raise HTTPException(status_code=400, detail="Request list cannot be empty")
        
        if len(requests) > 10:
            raise HTTPException(status_code=400, detail="Maximum 10 tasks per batch")
        
        # 创建批量任务
        task = create_task(len(requests))
        
        async def _run():
            try:
                # 定义单个任务处理函数
                async def process_request(req: CreateVideoTaskRequest, index: int):
                    from app.api.v1.chat import ChatCompletionRequest, VideoConfig, validate_request
                    from app.services.grok.services.media import VideoService
                    
                    # 构建请求体
                    body = {
                        "model": req.model,
                        "messages": [{"role": "user", "content": req.prompt}],
                        "video_config": {
                            "aspect_ratio": req.aspect_ratio,
                            "video_length": req.video_length,
                            "resolution_name": req.resolution,
                            "preset": req.preset
                        }
                    }
                    
                    # 验证请求
                    try:
                        chat_req = ChatCompletionRequest.model_validate(body)
                        validate_request(chat_req)
                        model_info = ModelService.get(chat_req.model)
                        if not model_info or not model_info.is_video:
                            return {"ok": False, "error": "Only video models are supported"}
                    except Exception as e:
                        return {"ok": False, "error": str(e)}
                    
                    # 创建视频任务
                    job = create_video_job()
                    job.request_payload = {
                        "model": req.model,
                        "messages": [{"role": "user", "content": req.prompt}],
                        "video_config": {
                            "aspect_ratio": req.aspect_ratio,
                            "video_length": req.video_length,
                            "resolution_name": req.resolution,
                            "preset": req.preset
                        }
                    }
                    
                    # 执行视频生成
                    def progress_callback(progress: int, result: Optional[dict] = None) -> None:
                        if result is not None:
                            # 处理结果，确保视频链接正确提取
                            if isinstance(result, dict):
                                # 支持多种视频链接格式
                                video_url = None
                                thumbnail_url = None
                                
                                # 情况1：result 直接包含 video_url
                                if "video_url" in result:
                                    video_url = result["video_url"]
                                    thumbnail_url = result.get("thumbnail_url", "")
                                # 情况2：result.choices[0].message.content 格式
                                elif "choices" in result:
                                    choices = result.get("choices", [])
                                    if choices and len(choices) > 0:
                                        message = choices[0].get("message", {})
                                        content = message.get("content", "")
                                        
                                        # 如果内容是HTML格式，提取视频URL
                                        if "<video" in content and "src=" in content:
                                            import re
                                            match = re.search(r'src="([^"]+)"', content)
                                            if match:
                                                video_url = match.group(1)
                                                # 尝试提取缩略图URL
                                                poster_match = re.search(r'poster="([^"]+)"', content)
                                                if poster_match:
                                                    thumbnail_url = poster_match.group(1)
                                        # 如果内容是纯URL
                                        elif content.startswith("http"):
                                            video_url = content
                                # 情况3：result 直接包含 content
                                elif "content" in result:
                                    content = result.get("content", "")
                                    if content.startswith("http"):
                                        video_url = content
                                
                                # 如果找到了视频链接，确保结果中包含
                                if video_url:
                                    result["video_url"] = video_url
                                    if thumbnail_url:
                                        result["thumbnail_url"] = thumbnail_url
                            
                            job.finish(result)
                        else:
                            job.set_running(progress) if job.status == "pending" else job.set_progress(progress)
                    
                    try:
                        job.set_running(0)
                        
                        # 执行视频生成
                        v_conf = chat_req.video_config or VideoConfig()
                        stream = await VideoService.completions(
                            model=chat_req.model,
                            messages=[m.model_dump() for m in chat_req.messages],
                            stream=True,
                            thinking=chat_req.thinking,
                            aspect_ratio=v_conf.aspect_ratio,
                            video_length=v_conf.video_length,
                            resolution=v_conf.resolution_name,
                            preset=v_conf.preset,
                            progress_callback=progress_callback,
                        )
                        async for _ in stream:
                            pass
                        
                        if job.status == "running":
                            job.fail("Stream ended without result")
                            return {"ok": False, "task_id": job.id, "error": "Stream ended without result"}
                        elif job.status == "completed":
                            return {"ok": True, "task_id": job.id, "result": job.result}
                        else:
                            return {"ok": False, "task_id": job.id, "error": job.error}
                            
                    except Exception as e:
                        logger.error(f"Batch video generation failed: {e}")
                        job.fail(str(e))
                        return {"ok": False, "task_id": job.id, "error": str(e)}
                    finally:
                        # 任务完成后设置过期时间
                        asyncio.create_task(expire_video_job(job.id, 3600))
                
                # 执行批量任务
                results = []
                for i, req in enumerate(requests):
                    if task.cancelled:
                        break
                    
                    try:
                        result = await process_request(req, i)
                        results.append(result)
                        task.record(result["ok"], item=f"Task {i+1}", detail=result)
                    except Exception as e:
                        error_msg = str(e)
                        results.append({"ok": False, "error": error_msg})
                        task.record(False, item=f"Task {i+1}", error=error_msg)
                
                if task.cancelled:
                    task.finish_cancelled()
                    return
                
                # 统计结果
                ok_count = sum(1 for r in results if r.get("ok"))
                fail_count = len(results) - ok_count
                
                # 构建响应
                result = {
                    "status": "success",
                    "summary": {
                        "total": len(requests),
                        "ok": ok_count,
                        "fail": fail_count,
                    },
                    "results": results,
                }
                
                task.finish(result)
                
            except Exception as e:
                task.fail_task(str(e))
            finally:
                asyncio.create_task(expire_task(task.id, 300))
        
        # 启动异步任务
        asyncio.create_task(_run())
        
        return {
            "status": "success",
            "task_id": task.id,
            "total": len(requests),
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Create batch video tasks failed: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to create batch video tasks: {str(e)}")


@router.get("/video/tasks/batch/{task_id}/stream")
async def stream_batch_video_tasks(
    task_id: str,
    request: Request,
):
    """
    流式获取批量视频任务进度
    """
    try:
        task = get_task(task_id)
        if not task:
            raise HTTPException(status_code=404, detail="Batch task not found")
        
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
                    if event.get("type") in ("done", "error", "cancelled"):
                        return
            finally:
                task.detach(queue)
        
        return StreamingResponse(
            event_stream(),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "Connection": "keep-alive"},
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Stream batch video tasks failed: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to stream batch video tasks: {str(e)}")


@router.post("/video/tasks/batch/{task_id}/cancel")
async def cancel_batch_video_tasks(
    task_id: str,
):
    """
    取消批量视频任务
    """
    try:
        task = get_task(task_id)
        if not task:
            raise HTTPException(status_code=404, detail="Batch task not found")
        
        task.cancel()
        return {"status": "success", "message": "Batch video task cancelled"}
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Cancel batch video tasks failed: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to cancel batch video tasks: {str(e)}")
