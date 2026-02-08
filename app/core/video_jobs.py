"""
视频异步任务存储：用于外部提交视频生成任务并查询进度/结果。
"""

from __future__ import annotations

import asyncio
import time
import uuid
from typing import Any, Dict, List, Optional


class VideoJob:
    """单个视频生成任务"""

    def __init__(self) -> None:
        self.id = uuid.uuid4().hex
        self.status = "pending"  # pending | running | completed | failed | cancelled
        self.progress = 0  # 0-100
        self.result: Optional[Dict[str, Any]] = None
        self.error: Optional[str] = None
        self.created_at = time.time()
        self.completed_at: Optional[float] = None
        self.request_payload: Optional[Dict[str, Any]] = None  # 提交时的请求摘要，便于列表展示
        self._queues: List[asyncio.Queue] = []

    def snapshot(self) -> Dict[str, Any]:
        out: Dict[str, Any] = {
            "job_id": self.id,
            "type": "video",
            "status": self.status,
            "progress": self.progress,
            "created_at": self.created_at,
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

    def attach(self) -> asyncio.Queue:
        q: asyncio.Queue = asyncio.Queue(maxsize=64)
        self._queues.append(q)
        return q

    def detach(self, q: asyncio.Queue) -> None:
        if q in self._queues:
            self._queues.remove(q)

    def _broadcast(self, event: Dict[str, Any]) -> None:
        for queue in list(self._queues):
            try:
                queue.put_nowait(event)
            except Exception:
                pass

    def set_running(self, progress: int = 0) -> None:
        self.status = "running"
        self.progress = min(100, max(0, progress))
        self._broadcast({"type": "progress", "job_id": self.id, "status": self.status, "progress": self.progress})

    def set_progress(self, progress: int) -> None:
        self.progress = min(100, max(0, progress))
        self._broadcast({"type": "progress", "job_id": self.id, "status": self.status, "progress": self.progress})

    def finish(self, result: Dict[str, Any]) -> None:
        self.status = "completed"
        self.progress = 100
        self.result = result
        self.completed_at = time.time()
        self._broadcast({
            "type": "completed",
            "job_id": self.id,
            "status": self.status,
            "progress": 100,
            "result": result,
        })

    def fail(self, error: str) -> None:
        self.status = "failed"
        self.error = error
        self.completed_at = time.time()
        self._broadcast({
            "type": "failed",
            "job_id": self.id,
            "status": self.status,
            "error": error,
        })


_JOBS: Dict[str, VideoJob] = {}
_JOBS_LOCK = asyncio.Lock()


def create_video_job() -> VideoJob:
    job = VideoJob()
    _JOBS[job.id] = job
    return job


def get_video_job(job_id: str) -> Optional[VideoJob]:
    return _JOBS.get(job_id)


def delete_video_job(job_id: str) -> None:
    _JOBS.pop(job_id, None)


async def expire_video_job(job_id: str, delay: int = 3600) -> None:
    """可选：一段时间后清理已完成/失败的任务"""
    await asyncio.sleep(delay)
    delete_video_job(job_id)


def list_all_video_jobs() -> List[Dict[str, Any]]:
    """列出所有视频任务（按创建时间倒序）"""
    jobs = sorted(_JOBS.values(), key=lambda j: j.created_at, reverse=True)
    return [j.snapshot() for j in jobs]


def clear_all_video_jobs() -> int:
    """清空所有视频任务，返回删除数量"""
    n = len(_JOBS)
    _JOBS.clear()
    return n
