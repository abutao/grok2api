from typing import List, Optional, Any, Dict
import time
from fastapi import APIRouter, Query, HTTPException, Path as FastAPIPath, Depends, Response

from app.api.v1.video_async import (
    get_all_video_tasks,
    get_video_task,
    delete_video_tasks,
    clear_video_tasks,
)
from app.api.v1 import video_async as video_async_api
from app.api.v1.image_async import (
    get_all_image_tasks,
    get_image_task,
    delete_image_tasks,
    clear_image_tasks,
)
from app.api.v1 import image_async as image_async_api
from app.core.auth import verify_app_key
from pydantic import BaseModel, Field

router = APIRouter()


class TaskListItem(BaseModel):
    task_id: str
    type: str  # "video" | "image"
    status: str
    progress: int
    created_at: float
    error: Optional[str] = None
    result: Optional[Any] = None
    payload: Optional[Dict[str, Any]] = None


class TaskListResponse(BaseModel):
    total: int
    page: int
    size: int
    data: List[TaskListItem]


class BatchDeleteRequest(BaseModel):
    task_ids: List[str] = Field(..., min_items=1)


class ClearTasksRequest(BaseModel):
    type: Optional[str] = Field(None, pattern="^(video|image)$")
    status: Optional[str] = None


class AdminAsyncCreateRequest(BaseModel):
    type: str = Field(..., pattern="^(video|image)$")
    payload: Dict[str, Any]


@router.post("/tasks/async", dependencies=[Depends(verify_app_key)])
async def create_admin_task(req: AdminAsyncCreateRequest, response: Response):
    if req.type == "video":
        task_id = await video_async_api.create_video_task_from_payload(req.payload)
    else:
        task_id = await image_async_api.create_image_task_from_payload(req.payload)

    status_path = f"/v1/admin/tasks/{task_id}/status"
    response.headers["Location"] = status_path
    response.headers["Operation-Location"] = f"{status_path}/result"
    return {"code": 200, "message": "任务已提交", "data": {"taskId": task_id}}


@router.get("/tasks/{task_id}/status", dependencies=[Depends(verify_app_key)])
async def get_admin_task_status(task_id: str):
    v_task = await get_video_task(task_id)
    if v_task:
        return await video_async_api.get_video_task_status(task_id)
    i_task = await get_image_task(task_id)
    if i_task:
        return await image_async_api.get_image_task_status(task_id)
    raise HTTPException(status_code=404, detail="Task not found")


@router.get("/tasks/{task_id}/result", dependencies=[Depends(verify_app_key)])
async def get_admin_task_result(task_id: str):
    v_task = await get_video_task(task_id)
    if v_task:
        return await video_async_api.get_video_task_result(task_id)
    i_task = await get_image_task(task_id)
    if i_task:
        return await image_async_api.get_image_task_result(task_id)
    raise HTTPException(status_code=404, detail="Task not found")


@router.post("/tasks/batch/delete", dependencies=[Depends(verify_app_key)])
async def batch_delete_tasks(req: BatchDeleteRequest):
    """批量删除任务"""
    deleted_count = 0
    
    # 尝试在两个池子中删除
    deleted_count += await delete_video_tasks(req.task_ids)
    deleted_count += await delete_image_tasks(req.task_ids)
    
    return {"code": 200, "message": f"已删除 {deleted_count} 个任务", "deleted": deleted_count}


@router.post("/tasks/clear", dependencies=[Depends(verify_app_key)])
async def clear_all_tasks(req: ClearTasksRequest):
    """清空任务（可按类型/状态）"""
    deleted_count = 0
    
    if req.type is None or req.type == "video":
        deleted_count += await clear_video_tasks(req.status)
        
    if req.type is None or req.type == "image":
        deleted_count += await clear_image_tasks(req.status)
        
    return {"code": 200, "message": f"已清空 {deleted_count} 个任务", "deleted": deleted_count}


@router.get("/tasks", response_model=TaskListResponse)
async def list_tasks(
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=100),
    type: Optional[str] = Query(None, pattern="^(video|image)$"),
    status: Optional[str] = Query(None),
    sort_by: str = Query("created_at", pattern="^(created_at)$"),
    order: str = Query("desc", pattern="^(asc|desc)$"),
):
    """
    获取任务列表（支持分页、筛选、排序）
    """
    tasks: List[TaskListItem] = []

    # 1. 收集所有任务
    if type is None or type == "video":
        video_tasks = await get_all_video_tasks()
        for t in video_tasks:
            tasks.append(
                TaskListItem(
                    task_id=t.id,
                    type="video",
                    status=t.status,
                    progress=t.progress,
                    created_at=t.created_at,
                    error=t.error,
                    result=t.result,
                    payload=t.request_payload,
                )
            )

    if type is None or type == "image":
        image_tasks = await get_all_image_tasks()
        for t in image_tasks:
            tasks.append(
                TaskListItem(
                    task_id=t.id,
                    type="image",
                    status=t.status,
                    progress=t.progress,
                    created_at=t.created_at,
                    error=t.error,
                    result=t.result,
                    payload=t.request_payload,
                )
            )

    # 2. 筛选
    if status:
        tasks = [t for t in tasks if t.status == status]

    # 3. 排序
    reverse = order == "desc"
    tasks.sort(key=lambda x: getattr(x, sort_by), reverse=reverse)

    # 4. 分页
    total = len(tasks)
    start = (page - 1) * size
    end = start + size
    paginated_tasks = tasks[start:end]

    return {
        "total": total,
        "page": page,
        "size": size,
        "data": paginated_tasks,
    }


@router.get("/tasks/{task_id}", response_model=TaskListItem)
async def get_task_detail(task_id: str = FastAPIPath(..., description="任务ID")):
    """
    获取任务详情
    """
    # 尝试查找视频任务
    v_task = await get_video_task(task_id)
    if v_task:
        return TaskListItem(
            task_id=v_task.id,
            type="video",
            status=v_task.status,
            progress=v_task.progress,
            created_at=v_task.created_at,
            error=v_task.error,
            result=v_task.result,
            payload=v_task.request_payload,
        )

    # 尝试查找图片任务
    i_task = await get_image_task(task_id)
    if i_task:
        return TaskListItem(
            task_id=i_task.id,
            type="image",
            status=i_task.status,
            progress=i_task.progress,
            created_at=i_task.created_at,
            error=i_task.error,
            result=i_task.result,
            payload=i_task.request_payload,
        )

    raise HTTPException(status_code=404, detail="Task not found")
