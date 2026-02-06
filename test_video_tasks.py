"""
测试视频任务 API
"""

import requests
import time
import json

BASE_URL = "http://localhost:8000"
API_KEY = "sk-D2jm4Z0kSTML2eovGrpGyehCXkr_aYS45JIxGYwYTAg"

headers = {
    "Content-Type": "application/json",
    "Authorization": f"Bearer {API_KEY}"
}

print("=" * 60)
print("测试 1: 创建视频任务")
print("=" * 60)

task_request = {
    "model": "grok-imagine-1.0-video",
    "prompt": "一只在太空漂浮的猫，周围有星星和星云",
    "video_config": {
        "aspect_ratio": "16:9",
        "video_length": 10,
        "resolution_name": "720p",
        "preset": "normal"
    }
}

response = requests.post(
    f"{BASE_URL}/v1/video/tasks",
    headers=headers,
    json=task_request
)

print(f"状态码: {response.status_code}")
print(f"响应: {json.dumps(response.json(), indent=2, ensure_ascii=False)}")

if response.status_code == 200:
    task_id = response.json()["task_id"]
    print(f"\n任务 ID: {task_id}")
    
    print("\n" + "=" * 60)
    print("测试 2: 查询任务状态")
    print("=" * 60)
    
    for i in range(5):
        response = requests.get(
            f"{BASE_URL}/v1/video/tasks/{task_id}",
            headers=headers
        )
        
        print(f"\n第 {i+1} 次查询:")
        print(f"状态码: {response.status_code}")
        print(f"响应: {json.dumps(response.json(), indent=2, ensure_ascii=False)}")
        
        if response.status_code == 200:
            status = response.json()["status"]
            if status in ["completed", "failed", "cancelled"]:
                break
        
        time.sleep(2)
    
    print("\n" + "=" * 60)
    print("测试 3: 列出所有任务")
    print("=" * 60)
    
    response = requests.get(
        f"{BASE_URL}/v1/video/tasks",
        headers=headers
    )
    
    print(f"状态码: {response.status_code}")
    print(f"响应: {json.dumps(response.json(), indent=2, ensure_ascii=False)}")
    
    print("\n" + "=" * 60)
    print("测试 4: 取消任务")
    print("=" * 60)
    
    response = requests.delete(
        f"{BASE_URL}/v1/video/tasks/{task_id}",
        headers=headers
    )
    
    print(f"状态码: {response.status_code}")
    print(f"响应: {json.dumps(response.json(), indent=2, ensure_ascii=False)}")
else:
    print("创建任务失败，跳过后续测试")

print("\n" + "=" * 60)
print("测试完成")
print("=" * 60)
