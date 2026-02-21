"""
Video async tasks API
"""

from __future__ import annotations

import asyncio
import re
import time
import uuid
from typing import Any, Dict, Optional

import orjson

from fastapi import APIRouter, HTTPException, Request, Response, status
from pydantic import BaseModel

from app.api.v1.chat import ChatCompletionRequest, VideoConfig, validate_request
from app.core.logger import logger
from app.services.grok.services.model import ModelService
from app.services.grok.services.video import VideoService

router = APIRouter(tags=["Video"])


class VideoAsyncCreateData(BaseModel):
    taskId: str


class VideoAsyncCreateResponse(BaseModel):
    code: int = 200
    message: str = "任务已提交"
    data: VideoAsyncCreateData


class VideoAsyncResultData(BaseModel):
    downloadUrl: Optional[str] = None


class VideoAsyncStatusData(BaseModel):
    taskId: str
    status: str
    progress: int
    result: Optional[VideoAsyncResultData] = None
    errorMsg: Optional[str] = None


class VideoAsyncStatusResponse(BaseModel):
    code: int = 200
    data: VideoAsyncStatusData


class VideoAsyncResultResponse(BaseModel):
    code: int = 200
    data: VideoAsyncStatusData


class VideoTask:
    def __init__(self) -> None:
        self.id = uuid.uuid4().hex
        self.status = "pending"
        self.progress = 0
        self.result: Optional[Dict[str, Any]] = None
        self.error: Optional[str] = None
        self.created_at = time.time()
        self.completed_at: Optional[float] = None
        self.request_payload: Optional[Dict[str, Any]] = None

    def snapshot(self) -> Dict[str, Any]:
        out: Dict[str, Any] = {
            "task_id": self.id,
            "status": self.status,
            "progress": self.progress,
        }
        if self.request_payload is not None:
            out["request_payload"] = self.request_payload
        if self.result is not None:
            out["result"] = self.result
        if self.error is not None:
            out["error"] = self.error
        if self.completed_at is not None:
            out["completed_at"] = self.completed_at
        return out

    def set_running(self, progress: int = 0) -> None:
        self.status = "running"
        self.progress = min(100, max(0, progress))

    def finish(self, result: Dict[str, Any]) -> None:
        self.status = "completed"
        self.progress = 100
        self.result = result
        self.completed_at = time.time()

    def fail(self, error: str) -> None:
        self.status = "failed"
        self.error = error
        self.completed_at = time.time()


_TASKS: Dict[str, VideoTask] = {}
_TASKS_LOCK = asyncio.Lock()


async def create_video_task() -> VideoTask:
    task = VideoTask()
    async with _TASKS_LOCK:
        _TASKS[task.id] = task
    return task


async def get_video_task(task_id: str) -> Optional[VideoTask]:
    async with _TASKS_LOCK:
        return _TASKS.get(task_id)


async def delete_video_task(task_id: str) -> None:
    async with _TASKS_LOCK:
        _TASKS.pop(task_id, None)


async def get_all_video_tasks() -> list[VideoTask]:
    async with _TASKS_LOCK:
        return list(_TASKS.values())


async def delete_video_tasks(task_ids: list[str]) -> int:
    count = 0
    async with _TASKS_LOCK:
        for tid in task_ids:
            if tid in _TASKS:
                _TASKS.pop(tid)
                count += 1
    return count


async def clear_video_tasks(status_filter: Optional[str] = None) -> int:
    count = 0
    async with _TASKS_LOCK:
        to_delete = []
        for tid, task in _TASKS.items():
            if status_filter is None or task.status == status_filter:
                to_delete.append(tid)
        
        for tid in to_delete:
            _TASKS.pop(tid)
            count += 1
    return count


async def expire_video_task(task_id: str, delay: int = 3600) -> None:
    await asyncio.sleep(delay)
    await delete_video_task(task_id)


def _normalize_async_payload(body: Dict[str, Any]) -> Dict[str, Any]:
    if "prompt" in body and "messages" not in body:
        prompt = body.get("prompt", "")
        aspect_ratio = body.get("aspect_ratio", "3:2")
        resolution_name = body.get("resolution_name", body.get("resolution", "480p"))
        video_length = body.get("video_length", 6)
        preset = body.get("preset", "normal")
        body = {
            "model": body.get("model", "grok-imagine-1.0-video"),
            "messages": [{"role": "user", "content": prompt}],
            "video_config": {
                "aspect_ratio": aspect_ratio,
                "video_length": video_length,
                "resolution_name": resolution_name,
                "preset": preset,
            },
        }
    return body


def _extract_video_urls(result: Dict[str, Any]) -> tuple[Optional[str], Optional[str]]:
    if not result:
        return None, None
    if "video_url" in result:
        return result.get("video_url"), result.get("thumbnail_url")
    content = None
    if "choices" in result:
        choices = result.get("choices", [])
        if choices:
            message = choices[0].get("message", {})
            content = message.get("content", "")
    elif "content" in result:
        content = result.get("content", "")
    if not content:
        return None, None
    if "<video" in content and "src=" in content:
        match = re.search(r'src="([^"]+)"', content)
        if match:
            video_url = match.group(1)
            poster_match = re.search(r'poster="([^"]+)"', content)
            thumbnail_url = poster_match.group(1) if poster_match else None
            return video_url, thumbnail_url
    md_match = re.findall(r"\[video\]\(([^)]+)\)", content)
    if md_match:
        return md_match[-1], None
    url_match = re.findall(r"https?://[^\s<)]+", content)
    if url_match:
        return url_match[-1], None
    return None, None


async def create_video_task_from_payload(body: Dict[str, Any]) -> str:
    body = _normalize_async_payload(body)

    try:
        req = ChatCompletionRequest.model_validate(body)
    except Exception as e:
        raise HTTPException(status_code=422, detail=str(e))

    validate_request(req)
    model_info = ModelService.get(req.model)
    if not model_info or not model_info.is_video:
        raise HTTPException(
            status_code=400,
            detail="Only video models are supported for async video generation",
        )

    v_conf = req.video_config or VideoConfig()
    task = await create_video_task()
    task.request_payload = {
        "model": req.model,
        "messages": [
            {
                "role": m.role,
                "content": m.content,
            }
            for m in req.messages
        ],
        "video_config": {
            "aspect_ratio": v_conf.aspect_ratio,
            "video_length": v_conf.video_length,
            "resolution_name": v_conf.resolution_name,
            "preset": v_conf.preset,
        },
    }

    async def run_video() -> None:
        task.set_running(0)
        try:
            stream = await VideoService.completions(
                model=req.model,
                messages=[m.model_dump() for m in req.messages],
                stream=True,
                reasoning_effort=req.reasoning_effort,
                aspect_ratio=v_conf.aspect_ratio,
                video_length=v_conf.video_length,
                resolution=v_conf.resolution_name,
                preset=v_conf.preset,
            )

            content_buffer = ""
            async for chunk in stream:
                if not chunk:
                    continue
                line = chunk.strip()
                if not line.startswith("data:"):
                    continue
                data_str = line[5:].strip()
                if data_str == "[DONE]":
                    continue
                try:
                    data = orjson.loads(data_str)
                    choices = data.get("choices", [])
                    if choices:
                        text = choices[0].get("delta", {}).get("content", "")
                        if text:
                            content_buffer += text
                            # 从流文本中解析 Grok 推送的进度数字
                            matches = list(re.finditer(r"进度\s*(\d+)%", content_buffer))
                            if matches:
                                progress = int(matches[-1].group(1))
                                task.set_running(min(progress, 99))
                except Exception:
                    continue

            result = {
                "id": f"chatcmpl-{uuid.uuid4().hex[:24]}",
                "object": "chat.completion",
                "created": int(time.time()),
                "model": req.model,
                "choices": [
                    {
                        "index": 0,
                        "message": {"role": "assistant", "content": content_buffer},
                        "logprobs": None,
                        "finish_reason": "stop",
                    }
                ],
                "usage": {"total_tokens": 0, "input_tokens": 0, "output_tokens": 0},
            }
            task.finish(result)
        except Exception as e:
            logger.exception("Video async task failed: %s", e)
            task.fail(str(e))
        finally:
            asyncio.create_task(expire_video_task(task.id, 86400))

    asyncio.create_task(run_video())
    return task.id


@router.post(
    "/video/generations/async",
    status_code=status.HTTP_202_ACCEPTED,
    response_model=VideoAsyncCreateResponse,
    response_model_exclude_none=True,
    operation_id="create_video_task",
    openapi_extra={
        "requestBody": {
            "required": True,
            "content": {
                "application/json": {
                    "schema": {
                        "type": "object",
                        "properties": {
                            "model": {"type": "string"},
                            "messages": {"type": "array"},
                            "prompt": {"type": "string"},
                            "video_config": {"type": "object"},
                            "aspect_ratio": {"type": "string"},
                            "video_length": {"type": "integer"},
                            "resolution_name": {"type": "string"},
                            "preset": {"type": "string"},
                            "reasoning_effort": {"type": "string"},
                            "callback_url": {"type": "string"},
                        },
                    }
                }
            },
        },
        "callbacks": {
            "taskComplete": {
                "{$request.body#/callback_url}": {
                    "post": {
                        "requestBody": {
                            "content": {
                                "application/json": {
                                    "schema": {
                                        "type": "object",
                                        "properties": {
                                            "taskId": {"type": "string"},
                                            "status": {"type": "string"},
                                            "downloadUrl": {"type": "string"},
                                        },
                                    }
                                }
                            }
                        },
                        "responses": {"200": {"description": "Callback received"}},
                    }
                }
            }
        },
        "responses": {
            "202": {
                "headers": {
                    "Location": {"schema": {"type": "string"}},
                    "Operation-Location": {"schema": {"type": "string"}},
                },
                "links": {
                    "GetTaskStatus": {
                        "operationId": "get_video_task_status",
                        "parameters": {"task_id": "$response.body#/data/taskId"},
                    },
                    "GetTaskResult": {
                        "operationId": "get_video_task_result",
                        "parameters": {"task_id": "$response.body#/data/taskId"},
                    },
                },
            }
        },
    },
)
async def video_generations_async(request: Request, response: Response):
    body = await request.json()
    task_id = await create_video_task_from_payload(body)
    status_path = f"/v1/video/tasks/{task_id}"
    response.headers["Location"] = status_path
    response.headers["Operation-Location"] = f"{status_path}/result"
    return {"code": 200, "message": "任务已提交", "data": {"taskId": task_id}}


@router.get(
    "/video/tasks",
    response_model_exclude_none=True,
    operation_id="list_video_tasks",
)
async def list_video_tasks():
    tasks = await get_all_video_tasks()
    status_map = {
        "pending": "pending",
        "running": "processing",
        "completed": "success",
        "failed": "failed",
        "cancelled": "failed",
    }
    result = []
    for task in tasks:
        video_url, _ = _extract_video_urls(task.result or {})
        result.append({
            "taskId": task.id,
            "status": status_map.get(task.status, "pending"),
            "progress": task.progress,
            "result": {"downloadUrl": video_url} if video_url else None,
            "errorMsg": task.error if task.status == "failed" else None,
        })
    return {"code": 200, "data": result, "total": len(result)}


@router.post(
    "/video/tasks",
    status_code=status.HTTP_202_ACCEPTED,
    response_model=VideoAsyncCreateResponse,
    response_model_exclude_none=True,
    operation_id="create_video_task_alias",
)
async def create_video_task_alias(request: Request, response: Response):
    """POST /v1/video/tasks 兼容别名，等价于 POST /v1/video/generations/async"""
    body = await request.json()
    task_id = await create_video_task_from_payload(body)
    status_path = f"/v1/video/tasks/{task_id}"
    response.headers["Location"] = status_path
    response.headers["Operation-Location"] = f"{status_path}/result"
    return {"code": 200, "message": "任务已提交", "data": {"taskId": task_id}}


@router.get(
    "/video/tasks/{task_id}",
    response_model=VideoAsyncStatusResponse,
    response_model_exclude_none=True,
    operation_id="get_video_task_status",
)
async def get_video_task_status(task_id: str):
    task = await get_video_task(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    status_map = {
        "pending": "pending",
        "running": "processing",
        "completed": "success",
        "failed": "failed",
        "cancelled": "failed",
    }
    status = status_map.get(task.status, "pending")
    video_url, _ = _extract_video_urls(task.result or {})
    result = {"downloadUrl": video_url} if video_url else None
    error_msg = task.error if task.status == "failed" else None
    return {
        "code": 200,
        "data": {
            "taskId": task.id,
            "status": status,
            "progress": task.progress,
            "result": result,
            "errorMsg": error_msg,
        },
    }


@router.get(
    "/video/tasks/{task_id}/result",
    response_model=VideoAsyncResultResponse,
    response_model_exclude_none=True,
    operation_id="get_video_task_result",
)
async def get_video_task_result(task_id: str):
    task = await get_video_task(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    status_map = {
        "pending": "pending",
        "running": "processing",
        "completed": "success",
        "failed": "failed",
        "cancelled": "failed",
    }
    status = status_map.get(task.status, "pending")
    video_url, _ = _extract_video_urls(task.result or {})
    result = {"downloadUrl": video_url} if video_url else None
    error_msg = task.error if task.status == "failed" else None
    return {
        "code": 200,
        "data": {
            "taskId": task.id,
            "status": status,
            "progress": task.progress,
            "result": result,
            "errorMsg": error_msg,
        },
    }


__all__ = ["router"]
