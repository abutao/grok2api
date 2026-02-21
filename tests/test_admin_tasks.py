
import asyncio
import time
from fastapi.testclient import TestClient
from main import create_app
from app.api.v1.video_async import _TASKS as VIDEO_TASKS, VideoTask
from app.api.v1.image_async import _TASKS as IMAGE_TASKS, ImageTask
from app.core.config import get_config

# Mock config to bypass auth or set known key
# But auth middleware reads from config. 
# We can set environment variable or mock get_config.
# Or simpler: get the default app_key.

app = create_app()
client = TestClient(app)

def get_auth_headers():
    # In auth.py: DEFAULT_APP_KEY = "grok2api"
    # We can use that if config is default.
    return {"Authorization": "Bearer grok2api"}

def test_admin_tasks_list_empty():
    # Clear tasks
    VIDEO_TASKS.clear()
    IMAGE_TASKS.clear()
    
    response = client.get("/v1/admin/tasks", headers=get_auth_headers())
    assert response.status_code == 200
    data = response.json()
    assert data["total"] == 0
    assert data["data"] == []

def test_admin_tasks_list_with_data():
    # Inject video task
    v_task = VideoTask()
    v_task.status = "completed"
    v_task.progress = 100
    v_task.request_payload = {"prompt": "test video"}
    VIDEO_TASKS[v_task.id] = v_task
    
    # Inject image task
    i_task = ImageTask()
    i_task.status = "pending"
    i_task.request_payload = {"prompt": "test image"}
    IMAGE_TASKS[i_task.id] = i_task
    
    response = client.get("/v1/admin/tasks", headers=get_auth_headers())
    assert response.status_code == 200
    data = response.json()
    assert data["total"] == 2
    
    # Verify sort (created_at desc) - latest first
    # Both created almost same time, but let's check content
    ids = [item["task_id"] for item in data["data"]]
    assert v_task.id in ids
    assert i_task.id in ids
    
    # Verify type filter
    resp_video = client.get("/v1/admin/tasks?type=video", headers=get_auth_headers())
    assert resp_video.json()["total"] == 1
    assert resp_video.json()["data"][0]["type"] == "video"
    
    resp_image = client.get("/v1/admin/tasks?type=image", headers=get_auth_headers())
    assert resp_image.json()["total"] == 1
    assert resp_image.json()["data"][0]["type"] == "image"

def test_admin_task_detail():
    v_task = VideoTask()
    v_task.result = {"video_url": "http://example.com/vid.mp4"}
    VIDEO_TASKS[v_task.id] = v_task
    
    response = client.get(f"/v1/admin/tasks/{v_task.id}", headers=get_auth_headers())
    assert response.status_code == 200
    data = response.json()
    assert data["task_id"] == v_task.id
    assert data["result"]["video_url"] == "http://example.com/vid.mp4"

def test_admin_task_not_found():
    response = client.get("/v1/admin/tasks/nonexistent", headers=get_auth_headers())
    assert response.status_code == 404

def test_admin_tasks_batch_delete():
    # Setup
    VIDEO_TASKS.clear()
    v_task1 = VideoTask()
    v_task2 = VideoTask()
    VIDEO_TASKS[v_task1.id] = v_task1
    VIDEO_TASKS[v_task2.id] = v_task2
    
    # Delete one
    response = client.post(
        "/v1/admin/tasks/batch/delete", 
        headers=get_auth_headers(),
        json={"task_ids": [v_task1.id]}
    )
    assert response.status_code == 200
    assert response.json()["deleted"] == 1
    assert v_task1.id not in VIDEO_TASKS
    assert v_task2.id in VIDEO_TASKS

def test_admin_tasks_clear():
    # Setup
    VIDEO_TASKS.clear()
    IMAGE_TASKS.clear()
    
    v_task = VideoTask()
    v_task.status = "completed"
    VIDEO_TASKS[v_task.id] = v_task
    
    i_task = ImageTask()
    i_task.status = "failed"
    IMAGE_TASKS[i_task.id] = i_task
    
    # Clear only video
    response = client.post(
        "/v1/admin/tasks/clear", 
        headers=get_auth_headers(),
        json={"type": "video"}
    )
    assert response.status_code == 200
    assert response.json()["deleted"] == 1
    assert len(VIDEO_TASKS) == 0
    assert len(IMAGE_TASKS) == 1
    
    # Clear failed images
    response = client.post(
        "/v1/admin/tasks/clear", 
        headers=get_auth_headers(),
        json={"type": "image", "status": "failed"}
    )
    assert response.status_code == 200
    assert response.json()["deleted"] == 1
    assert len(IMAGE_TASKS) == 0

if __name__ == "__main__":
    try:
        test_admin_tasks_list_empty()
        print("test_admin_tasks_list_empty PASSED")
        
        test_admin_tasks_list_with_data()
        print("test_admin_tasks_list_with_data PASSED")
        
        test_admin_task_detail()
        print("test_admin_tasks_detail PASSED")
        
        test_admin_task_not_found()
        print("test_admin_task_not_found PASSED")
        
        test_admin_tasks_batch_delete()
        print("test_admin_tasks_batch_delete PASSED")
        
        test_admin_tasks_clear()
        print("test_admin_tasks_clear PASSED")
        
    except Exception as e:
        print(f"TEST FAILED: {e}")
        import traceback
        traceback.print_exc()
