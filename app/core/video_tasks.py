"""
Video task manager for async video generation.
"""

import asyncio
import json
import os
import time
import uuid
from typing import Any, Dict, Optional
from enum import Enum
from pathlib import Path

from app.core.logger import logger


TASKS_FILE = Path("data/video_tasks.json")
TASKS_FILE.parent.mkdir(parents=True, exist_ok=True)


class TaskStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class VideoTask:
    def __init__(
        self,
        model: str,
        prompt: str,
        aspect_ratio: str = "3:2",
        video_length: int = 6,
        resolution: str = "480p",
        preset: str = "normal",
        image_url: Optional[str] = None,
    ):
        self.id = uuid.uuid4().hex
        self.model = model
        self.prompt = prompt
        self.aspect_ratio = aspect_ratio
        self.video_length = video_length
        self.resolution = resolution
        self.preset = preset
        self.image_url = image_url
        
        self.status = TaskStatus.PENDING
        self.progress = 0
        self.message = ""
        self.video_url: Optional[str] = None
        self.thumbnail_url: Optional[str] = None
        self.error: Optional[str] = None
        
        self.created_at = time.time()
        self.started_at: Optional[float] = None
        self.completed_at: Optional[float] = None
        
        self._queues: list[asyncio.Queue] = []
        self._final_event: Optional[Dict[str, Any]] = None
        self.cancelled = False

    def snapshot(self) -> Dict[str, Any]:
        return {
            "task_id": self.id,
            "status": self.status.value,
            "progress": self.progress,
            "message": self.message,
            "prompt": self.prompt,
            "image_url": self.image_url,
            "video_url": self.video_url,
            "thumbnail_url": self.thumbnail_url,
            "error": self.error,
            "created_at": self.created_at,
            "started_at": self.started_at,
            "completed_at": self.completed_at,
        }

    def attach(self) -> asyncio.Queue:
        q: asyncio.Queue = asyncio.Queue(maxsize=200)
        self._queues.append(q)
        return q

    def detach(self, q: asyncio.Queue) -> None:
        if q in self._queues:
            self._queues.remove(q)

    def _publish(self, event: Dict[str, Any]) -> None:
        for q in list(self._queues):
            try:
                q.put_nowait(event)
            except Exception:
                pass

    def start(self) -> None:
        self.status = TaskStatus.RUNNING
        self.started_at = time.time()
        self.message = "开始生成视频"
        event = {
            "type": "status",
            "task_id": self.id,
            "status": self.status.value,
            "progress": self.progress,
            "message": self.message,
        }
        self._publish(event)

    def update_progress(self, progress: int, message: str = "") -> None:
        self.progress = progress
        if message:
            self.message = message
        event = {
            "type": "progress",
            "task_id": self.id,
            "status": self.status.value,
            "progress": self.progress,
            "message": self.message,
        }
        self._publish(event)

    def complete(self, video_url: str, thumbnail_url: str = "") -> None:
        self.status = TaskStatus.COMPLETED
        self.progress = 100
        self.video_url = video_url
        self.thumbnail_url = thumbnail_url
        self.completed_at = time.time()
        self.message = "视频生成完成"
        event = {
            "type": "completed",
            "task_id": self.id,
            "status": self.status.value,
            "progress": self.progress,
            "message": self.message,
            "video_url": self.video_url,
            "thumbnail_url": self.thumbnail_url,
        }
        self._final_event = event
        self._publish(event)

    def fail(self, error: str) -> None:
        self.status = TaskStatus.FAILED
        self.error = error
        self.completed_at = time.time()
        self.message = f"生成失败: {error}"
        event = {
            "type": "failed",
            "task_id": self.id,
            "status": self.status.value,
            "progress": self.progress,
            "message": self.message,
            "error": self.error,
        }
        self._final_event = event
        self._publish(event)

    def cancel(self) -> None:
        self.cancelled = True

    def finish_cancelled(self) -> None:
        self.status = TaskStatus.CANCELLED
        self.completed_at = time.time()
        self.message = "任务已取消"
        event = {
            "type": "cancelled",
            "task_id": self.id,
            "status": self.status.value,
            "progress": self.progress,
            "message": self.message,
        }
        self._final_event = event
        self._publish(event)

    def final_event(self) -> Optional[Dict[str, Any]]:
        return self._final_event


_TASKS: Dict[str, VideoTask] = {}


def create_task(
    model: str,
    prompt: str,
    aspect_ratio: str = "3:2",
    video_length: int = 6,
    resolution: str = "480p",
    preset: str = "normal",
    image_url: Optional[str] = None,
) -> VideoTask:
    task = VideoTask(
        model=model,
        prompt=prompt,
        aspect_ratio=aspect_ratio,
        video_length=video_length,
        resolution=resolution,
        preset=preset,
        image_url=image_url,
    )
    _TASKS[task.id] = task
    save_tasks()
    return task


def get_task(task_id: str) -> Optional[VideoTask]:
    return _TASKS.get(task_id)


def delete_task(task_id: str) -> None:
    _TASKS.pop(task_id, None)
    save_tasks()


def delete_tasks(task_ids: list[str]) -> int:
    count = 0
    for task_id in task_ids:
        if task_id in _TASKS:
            del _TASKS[task_id]
            count += 1
    save_tasks()
    return count


def delete_tasks_by_status(status: TaskStatus) -> int:
    count = 0
    to_delete = []
    for task_id, task in _TASKS.items():
        if task.status == status:
            to_delete.append(task_id)
    for task_id in to_delete:
        del _TASKS[task_id]
        count += 1
    save_tasks()
    return count


def clear_all_tasks() -> int:
    count = len(_TASKS)
    _TASKS.clear()
    save_tasks()
    return count


async def expire_task(task_id: str, delay: int = 3600) -> None:
    await asyncio.sleep(delay)
    delete_task(task_id)


def list_tasks(status: Optional[TaskStatus] = None) -> list[Dict[str, Any]]:
    tasks = []
    for task in _TASKS.values():
        if status is None or task.status == status:
            tasks.append(task.snapshot())
    return tasks


def save_tasks() -> None:
    try:
        tasks_data = []
        for task in _TASKS.values():
            tasks_data.append({
                "id": task.id,
                "model": task.model,
                "prompt": task.prompt,
                "aspect_ratio": task.aspect_ratio,
                "video_length": task.video_length,
                "resolution": task.resolution,
                "preset": task.preset,
                "image_url": task.image_url,
                "status": task.status.value,
                "progress": task.progress,
                "message": task.message,
                "video_url": task.video_url,
                "thumbnail_url": task.thumbnail_url,
                "error": task.error,
                "created_at": task.created_at,
                "started_at": task.started_at,
                "completed_at": task.completed_at,
            })
        
        with open(TASKS_FILE, "w", encoding="utf-8") as f:
            json.dump(tasks_data, f, ensure_ascii=False, indent=2)
    except Exception as e:
        logger.error(f"Failed to save tasks: {e}")


def load_tasks() -> None:
    try:
        if not TASKS_FILE.exists():
            return
        
        with open(TASKS_FILE, "r", encoding="utf-8") as f:
            tasks_data = json.load(f)
        
        for task_data in tasks_data:
            task = VideoTask(
                model=task_data["model"],
                prompt=task_data["prompt"],
                aspect_ratio=task_data.get("aspect_ratio", "3:2"),
                video_length=task_data.get("video_length", 6),
                resolution=task_data.get("resolution", "480p"),
                preset=task_data.get("preset", "normal"),
                image_url=task_data.get("image_url"),
            )
            task.id = task_data["id"]
            task.status = TaskStatus(task_data["status"])
            task.progress = task_data.get("progress", 0)
            task.message = task_data.get("message", "")
            task.video_url = task_data.get("video_url")
            task.thumbnail_url = task_data.get("thumbnail_url")
            task.error = task_data.get("error")
            task.created_at = task_data.get("created_at", time.time())
            task.started_at = task_data.get("started_at")
            task.completed_at = task_data.get("completed_at")
            
            _TASKS[task.id] = task
        
        logger.info(f"Loaded {len(tasks_data)} tasks from {TASKS_FILE}")
    except Exception as e:
        logger.error(f"Failed to load tasks: {e}")
