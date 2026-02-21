"""
Image async tasks API
"""

from __future__ import annotations

import asyncio
import time
import uuid
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException, Request, Response, status
from pydantic import BaseModel

from app.api.v1.image import (
    ImageGenerationRequest,
    resolve_aspect_ratio,
    resolve_response_format,
    response_field_name,
    validate_generation_request,
)
from app.core.exceptions import AppException, ErrorType
from app.core.logger import logger
from app.services.grok.services.image import ImageGenerationService
from app.services.grok.services.model import ModelService
from app.services.token import get_token_manager

router = APIRouter(tags=["Images"])


class ImageAsyncCreateData(BaseModel):
    taskId: str


class ImageAsyncCreateResponse(BaseModel):
    code: int = 200
    message: str = "任务已提交"
    data: ImageAsyncCreateData


class ImageAsyncResultData(BaseModel):
    images: Optional[List[str]] = None


class ImageAsyncStatusData(BaseModel):
    taskId: str
    status: str
    progress: int
    result: Optional[ImageAsyncResultData] = None
    errorMsg: Optional[str] = None


class ImageAsyncStatusResponse(BaseModel):
    code: int = 200
    data: ImageAsyncStatusData


class ImageAsyncResultResponse(BaseModel):
    code: int = 200
    data: ImageAsyncStatusData


class ImageTask:
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


_TASKS: Dict[str, ImageTask] = {}
_TASKS_LOCK = asyncio.Lock()


async def create_image_task() -> ImageTask:
    task = ImageTask()
    async with _TASKS_LOCK:
        _TASKS[task.id] = task
    return task


async def get_image_task(task_id: str) -> Optional[ImageTask]:
    async with _TASKS_LOCK:
        return _TASKS.get(task_id)


async def delete_image_task(task_id: str) -> None:
    async with _TASKS_LOCK:
        _TASKS.pop(task_id, None)


async def get_all_image_tasks() -> list[ImageTask]:
    async with _TASKS_LOCK:
        return list(_TASKS.values())


async def delete_image_tasks(task_ids: list[str]) -> int:
    count = 0
    async with _TASKS_LOCK:
        for tid in task_ids:
            if tid in _TASKS:
                _TASKS.pop(tid)
                count += 1
    return count


async def clear_image_tasks(status_filter: Optional[str] = None) -> int:
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


async def expire_image_task(task_id: str, delay: int = 3600) -> None:
    await asyncio.sleep(delay)
    await delete_image_task(task_id)


async def _get_token(model: str):
    token_mgr = await get_token_manager()
    await token_mgr.reload_if_stale()

    token = None
    for pool_name in ModelService.pool_candidates_for_model(model):
        token = token_mgr.get_token(pool_name)
        if token:
            break

    if not token:
        raise AppException(
            message="No available tokens. Please try again later.",
            error_type=ErrorType.RATE_LIMIT.value,
            code="rate_limit_exceeded",
            status_code=429,
        )

    return token_mgr, token


def _extract_images(result: Dict[str, Any]) -> Optional[List[str]]:
    if not result:
        return None
    data = result.get("data")
    if isinstance(data, list):
        images: List[str] = []
        for item in data:
            if isinstance(item, dict):
                for value in item.values():
                    if isinstance(value, str):
                        images.append(value)
                        break
            elif isinstance(item, str):
                images.append(item)
        return images or None
    return None


async def create_image_task_from_payload(body: Dict[str, Any]) -> str:
    try:
        req = ImageGenerationRequest.model_validate(body)
    except Exception as e:
        raise HTTPException(status_code=422, detail=str(e))

    validate_generation_request(req)
    model_info = ModelService.get(req.model)
    if not model_info or not model_info.is_image:
        raise HTTPException(
            status_code=400,
            detail="Only image models are supported for async image generation",
        )

    response_format_value = req.response_format
    if response_format_value == "base64":
        response_format_value = "b64_json"
    response_format = resolve_response_format(response_format_value)
    response_field = response_field_name(response_format)
    aspect_ratio = resolve_aspect_ratio(req.size)

    task = await create_image_task()
    task.request_payload = {
        "model": req.model,
        "prompt": req.prompt,
        "n": req.n,
        "size": req.size,
        "response_format": response_format,
        "stream": False,
    }

    async def run_image() -> None:
        task.set_running(0)
        try:
            token_mgr, token = await _get_token(req.model)
            result = await ImageGenerationService().generate(
                token_mgr=token_mgr,
                token=token,
                model_info=model_info,
                prompt=req.prompt,
                n=req.n,
                response_format=response_format,
                size=req.size,
                aspect_ratio=aspect_ratio,
                stream=False,
            )
            data = [{response_field: img} for img in result.data]
            usage = result.usage_override or {
                "total_tokens": 0,
                "input_tokens": 0,
                "output_tokens": 0,
                "input_tokens_details": {"text_tokens": 0, "image_tokens": 0},
            }
            task.finish(
                {
                    "created": int(time.time()),
                    "data": data,
                    "usage": usage,
                }
            )
        except Exception as e:
            logger.exception("Image async task failed: %s", e)
            task.fail(str(e))
        finally:
            asyncio.create_task(expire_image_task(task.id, 86400))

    asyncio.create_task(run_image())
    return task.id


@router.post(
    "/images/generations/async",
    status_code=status.HTTP_202_ACCEPTED,
    response_model=ImageAsyncCreateResponse,
    response_model_exclude_none=True,
    operation_id="create_image_task",
    openapi_extra={
        "requestBody": {
            "required": True,
            "content": {
                "application/json": {
                    "schema": {
                        "type": "object",
                        "properties": {
                            "model": {"type": "string"},
                            "prompt": {"type": "string"},
                            "n": {"type": "integer"},
                            "size": {"type": "string"},
                            "response_format": {"type": "string"},
                            "stream": {"type": "boolean"},
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
                                            "images": {"type": "array"},
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
                        "operationId": "get_image_task_status",
                        "parameters": {"task_id": "$response.body#/data/taskId"},
                    },
                    "GetTaskResult": {
                        "operationId": "get_image_task_result",
                        "parameters": {"task_id": "$response.body#/data/taskId"},
                    },
                },
            }
        },
    },
)
async def image_generations_async(request: Request, response: Response):
    body = await request.json()
    task_id = await create_image_task_from_payload(body)
    status_path = f"/v1/images/tasks/{task_id}"
    response.headers["Location"] = status_path
    response.headers["Operation-Location"] = f"{status_path}/result"
    return {"code": 200, "message": "任务已提交", "data": {"taskId": task_id}}


@router.get(
    "/images/tasks",
    response_model_exclude_none=True,
    operation_id="list_image_tasks",
)
async def list_image_tasks():
    tasks = await get_all_image_tasks()
    status_map = {
        "pending": "pending",
        "running": "processing",
        "completed": "success",
        "failed": "failed",
        "cancelled": "failed",
    }
    result = []
    for task in tasks:
        images = _extract_images(task.result or {})
        result.append({
            "taskId": task.id,
            "status": status_map.get(task.status, "pending"),
            "progress": task.progress,
            "result": {"images": images} if images else None,
            "errorMsg": task.error if task.status == "failed" else None,
        })
    return {"code": 200, "data": result, "total": len(result)}


@router.post(
    "/images/tasks",
    status_code=status.HTTP_202_ACCEPTED,
    response_model=ImageAsyncCreateResponse,
    response_model_exclude_none=True,
    operation_id="create_image_task_alias",
)
async def create_image_task_alias(request: Request, response: Response):
    """POST /v1/images/tasks 兼容别名，等价于 POST /v1/images/generations/async"""
    body = await request.json()
    task_id = await create_image_task_from_payload(body)
    status_path = f"/v1/images/tasks/{task_id}"
    response.headers["Location"] = status_path
    response.headers["Operation-Location"] = f"{status_path}/result"
    return {"code": 200, "message": "任务已提交", "data": {"taskId": task_id}}


@router.get(
    "/images/tasks/{task_id}",
    response_model=ImageAsyncStatusResponse,
    response_model_exclude_none=True,
    operation_id="get_image_task_status",
)
async def get_image_task_status(task_id: str):
    task = await get_image_task(task_id)
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
    images = _extract_images(task.result or {})
    result = {"images": images} if images else None
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
    "/images/tasks/{task_id}/result",
    response_model=ImageAsyncResultResponse,
    response_model_exclude_none=True,
    operation_id="get_image_task_result",
)
async def get_image_task_result(task_id: str):
    task = await get_image_task(task_id)
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
    images = _extract_images(task.result or {})
    result = {"images": images} if images else None
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
