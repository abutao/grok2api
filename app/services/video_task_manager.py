"""
Video task manager service.
"""

import asyncio
from typing import Optional

from app.core.video_tasks import (
    VideoTask,
    TaskStatus,
    create_task,
    get_task,
    delete_task,
    expire_task,
)
from app.services.grok.services.media import VideoService
from app.core.logger import logger
from app.core.exceptions import AppException, ErrorType


class VideoTaskManager:
    _instance: Optional["VideoTaskManager"] = None
    _lock = asyncio.Lock()

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self):
        if hasattr(self, "_initialized"):
            return
        self._initialized = True
        self._running_tasks: dict[str, asyncio.Task] = {}

    async def create_video_task(
        self,
        model: str,
        prompt: str,
        aspect_ratio: str = "3:2",
        video_length: int = 6,
        resolution: str = "480p",
        preset: str = "normal",
        image_url: Optional[str] = None,
    ) -> str:
        task = create_task(
            model=model,
            prompt=prompt,
            aspect_ratio=aspect_ratio,
            video_length=video_length,
            resolution=resolution,
            preset=preset,
            image_url=image_url,
        )

        async def _run_task():
            try:
                await self._execute_video_task(task)
            except Exception as e:
                logger.error(f"Video task {task.id} failed: {e}")
                task.fail(str(e))
            finally:
                if task.id in self._running_tasks:
                    del self._running_tasks[task.id]
                asyncio.create_task(expire_task(task.id, 3600))

        runner = asyncio.create_task(_run_task())
        self._running_tasks[task.id] = runner

        return task.id

    async def _execute_video_task(self, task: VideoTask) -> None:
        task.start()

        logger.info(f"Executing video task {task.id}: prompt='{task.prompt}', image_url={task.image_url}")

        try:
            from app.services.token import get_token_manager

            token_mgr = await get_token_manager()
            await token_mgr.reload_if_stale()
            token = None
            from app.services.grok.models.model import ModelService

            for pool_name in ModelService.pool_candidates_for_model(task.model):
                token = token_mgr.get_token(pool_name)
                if token:
                    break

            if not token:
                task.fail("No available tokens")
                return

            service = VideoService()

            final_image_url = task.image_url

            if task.image_url:
                logger.info(f"Processing image URL: {task.image_url}")
                
                if not task.image_url.startswith("https://assets.grok.com/"):
                    logger.info(f"Image is from external URL, uploading to Grok server...")
                    from app.services.grok.services.assets import UploadService
                    
                    upload_service = UploadService()
                    try:
                        file_id, file_uri = await upload_service.upload(task.image_url, token)
                        final_image_url = f"https://assets.grok.com/{file_uri}"
                        logger.info(f"Image uploaded to Grok successfully: {final_image_url}")
                    except Exception as e:
                        logger.error(f"Failed to upload image to Grok: {e}", exc_info=True)
                        task.fail(f"Upload authentication failed: {e}")
                        return
                    finally:
                        await upload_service.close()
                else:
                    logger.info(f"Image is from Grok, using it directly: {task.image_url}")

                logger.info(f"Generating video from image: {final_image_url}")
                response = await service.generate_from_image(
                    token,
                    task.prompt,
                    final_image_url,
                    task.aspect_ratio,
                    task.video_length,
                    task.resolution,
                    task.preset,
                )
            else:
                logger.info(f"Generating video from prompt: {task.prompt}")
                response = await service.generate(
                    token,
                    task.prompt,
                    task.aspect_ratio,
                    task.video_length,
                    task.resolution,
                    task.preset,
                )

            async for line in response:
                if task.cancelled:
                    task.finish_cancelled()
                    return

                import orjson

                try:
                    data = orjson.loads(line)
                except orjson.JSONDecodeError:
                    continue

                resp = data.get("result", {}).get("response", {})

                if video_resp := resp.get("streamingVideoGenerationResponse"):
                    progress = video_resp.get("progress", 0)
                    if progress > task.progress:
                        task.update_progress(progress, f"正在生成视频中，当前进度{progress}%")

                    if progress == 100:
                        video_url = video_resp.get("videoUrl", "")
                        thumbnail_url = video_resp.get("thumbnailImageUrl", "")

                        if video_url:
                            from app.services.grok.processors.processor import BaseProcessor

                            processor = BaseProcessor(task.model, token)
                            final_video_url = await processor.process_url(video_url, "video")
                            final_thumbnail_url = ""
                            if thumbnail_url:
                                final_thumbnail_url = await processor.process_url(
                                    thumbnail_url, "image"
                                )

                            task.complete(final_video_url, final_thumbnail_url)
                            
                            # 记录 token 使用
                            try:
                                from app.services.grok.models.model import ModelService
                                from app.services.token import EffortType
                                
                                model_info = ModelService.get(task.model)
                                effort = (
                                    EffortType.HIGH
                                    if (model_info and model_info.cost.value == "high")
                                    else EffortType.LOW
                                )
                                await token_mgr.consume(token, effort)
                                logger.info(
                                    f"Video task {task.id} completed, recorded usage for token {token[:10]}... (effort={effort.value})"
                                )
                            except Exception as e:
                                logger.warning(f"Failed to record video task usage: {e}")
                        else:
                            task.fail("No video URL in response")
                        return

        except AppException as e:
            task.fail(e.message)
        except Exception as e:
            logger.error(f"Video generation error: {e}", exc_info=True)
            task.fail(str(e))

    async def cancel_task(self, task_id: str) -> bool:
        task = get_task(task_id)
        if not task:
            return False

        task.cancel()
        if task_id in self._running_tasks:
            self._running_tasks[task_id].cancel()
        return True

    async def get_task_status(self, task_id: str) -> Optional[dict]:
        task = get_task(task_id)
        if not task:
            return None
        return task.snapshot()


async def get_video_task_manager() -> VideoTaskManager:
    return VideoTaskManager()
