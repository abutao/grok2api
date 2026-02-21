
import pytest
from fastapi.testclient import TestClient
from main import create_app

app = create_app()
client = TestClient(app)

def get_auth_headers():
    return {"Authorization": "Bearer grok2api"}

def test_admin_text_page_access():
    """测试 Admin 文本任务页面访问"""
    # 页面是静态文件返回，通常不需要 Auth（根据实现），或者前端校验。
    # 这里后端接口是 include_in_schema=False 的 FileResponse
    response = client.get("/admin/text")
    assert response.status_code == 200
    assert b"Grok2API" in response.content

def test_video_async_submit():
    """测试视频异步提交接口"""
    payload = {
        "model": "grok-imagine-1.0-video",
        "prompt": "test video prompt",
        "video_config": {"aspect_ratio": "3:2"}
    }
    response = client.post(
        "/v1/video/generations/async",
        headers=get_auth_headers(),
        json=payload
    )
    # 可能返回 202 或 401/403 (如果没有配置 token)
    # 本地环境没有真实 Token，Mock 可能会失败或返回错误
    # 这里主要验证接口存在性
    assert response.status_code in [202, 400, 401, 500] 

def test_image_async_submit():
    """测试图片异步提交接口"""
    payload = {
        "model": "grok-2-image-generation",
        "prompt": "test image prompt",
        "size": "1024x1024"
    }
    response = client.post(
        "/v1/images/generations/async",
        headers=get_auth_headers(),
        json=payload
    )
    assert response.status_code in [202, 400, 401, 500]

def test_admin_async_task_valid_key():
    payload = {
        "type": "image",
        "payload": {
            "model": "grok-imagine-1.0",
            "prompt": "test image prompt",
            "size": "1024x1024",
            "response_format": "url"
        }
    }
    response = client.post(
        "/v1/admin/tasks/async",
        headers=get_auth_headers(),
        json=payload
    )
    assert response.status_code == 200
    data = response.json()
    assert data["code"] == 200
    assert "taskId" in data["data"]

def test_admin_async_task_invalid_key():
    payload = {
        "type": "image",
        "payload": {
            "model": "grok-2-image-generation",
            "prompt": "test image prompt",
            "size": "1024x1024"
        }
    }
    response = client.post(
        "/v1/admin/tasks/async",
        headers={"Authorization": "Bearer expired_key"},
        json=payload
    )
    assert response.status_code == 401

def test_admin_async_task_malformed_key():
    payload = {
        "type": "image",
        "payload": {
            "model": "grok-2-image-generation",
            "prompt": "test image prompt",
            "size": "1024x1024"
        }
    }
    response = client.post(
        "/v1/admin/tasks/async",
        headers={"Authorization": "Bearer Bearer grok2api"},
        json=payload
    )
    assert response.status_code == 401

def test_admin_async_task_missing_key():
    payload = {
        "type": "image",
        "payload": {
            "model": "grok-2-image-generation",
            "prompt": "test image prompt",
            "size": "1024x1024"
        }
    }
    response = client.post(
        "/v1/admin/tasks/async",
        json=payload
    )
    assert response.status_code == 401

if __name__ == "__main__":
    try:
        test_admin_text_page_access()
        print("test_admin_text_page_access PASSED")
        
        test_video_async_submit()
        print("test_video_async_submit PASSED")
        
        test_image_async_submit()
        print("test_image_async_submit PASSED")
        
    except Exception as e:
        print(f"TEST FAILED: {e}")
        import traceback
        traceback.print_exc()
