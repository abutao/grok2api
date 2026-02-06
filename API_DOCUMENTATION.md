# Grok2API 外部 API 使用文档

## 基础信息

### Base URL
```
http://localhost:8000
```

### 认证
当前版本无需认证，所有 API 可直接访问。

### 响应格式
所有 API 返回 JSON 格式数据（SSE 流式响应除外）。

---

## 1. 聊天补全 API

### 1.1 创建聊天补全

**端点**: `POST /chat/completions`

**描述**: 兼容 OpenAI 的聊天补全 API，支持文本对话和视频生成。

#### 请求参数

| 参数 | 类型 | 必填 | 描述 |
|------|------|------|------|
| `model` | string | 是 | 模型名称 |
| `messages` | array | 是 | 消息数组 |
| `stream` | boolean | 否 | 是否流式输出 |
| `thinking` | string | 否 | 思考模式: `enabled`/`disabled`/`null` |
| `video_config` | object | 否 | 视频生成配置（仅视频模型） |

#### 消息格式

```json
{
  "role": "user|assistant|system|tool",
  "content": "string or array"
}
```

#### 视频配置

```json
{
  "aspect_ratio": "3:2|16:9|1:1|9:16|2:3",
  "video_length": 6|10,
  "resolution_name": "480p|720p",
  "preset": "fun|normal|spicy|custom"
}
```

#### 请求示例

**文本对话**:
```bash
curl -X POST http://localhost:8000/chat/completions \
  -H "Content-Type: application/json" \
  -d '{
    "model": "grok-2",
    "messages": [
      {"role": "user", "content": "你好，请介绍一下你自己"}
    ]
  }'
```

**视频生成**:
```bash
curl -X POST http://localhost:8000/chat/completions \
  -H "Content-Type: application/json" \
  -d '{
    "model": "grok-imagine-1.0-video",
    "messages": [
      {"role": "user", "content": "一只可爱的猫在花园里玩耍"}
    ],
    "video_config": {
      "aspect_ratio": "16:9",
      "video_length": 6,
      "resolution_name": "480p",
      "preset": "normal"
    }
  }'
```

**流式响应**:
```bash
curl -X POST http://localhost:8000/chat/completions \
  -H "Content-Type: application/json" \
  -d '{
    "model": "grok-2",
    "messages": [
      {"role": "user", "content": "写一首诗"}
    ],
    "stream": true
  }'
```

#### 响应示例

**非流式响应**:
```json
{
  "id": "chatcmpl-xxx",
  "object": "chat.completion",
  "created": 1234567890,
  "model": "grok-2",
  "choices": [
    {
      "index": 0,
      "message": {
        "role": "assistant",
        "content": "你好！我是 Grok，由 xAI 开发的 AI 助手..."
      },
      "finish_reason": "stop"
    }
  ],
  "usage": {
    "prompt_tokens": 10,
    "completion_tokens": 20,
    "total_tokens": 30
  }
}
```

**流式响应 (SSE)**:
```
data: {"id":"chatcmpl-xxx","object":"chat.completion.chunk","choices":[{"index":0,"delta":{"content":"你好"}}]}

data: {"id":"chatcmpl-xxx","object":"chat.completion.chunk","choices":[{"index":0,"delta":{"content":"！"}}]}

data: [DONE]
```

---

## 2. 图片生成 API

### 2.1 创建图片

**端点**: `POST /images/generations`

**描述**: 根据文本描述生成图片。

#### 请求参数

| 参数 | 类型 | 必填 | 默认值 | 描述 |
|------|------|------|--------|------|
| `prompt` | string | 是 | - | 图片描述 |
| `model` | string | 否 | `grok-imagine-1.0` | 模型名称 |
| `n` | integer | 否 | `1` | 生成数量 (1-10) |
| `size` | string | 否 | `1024x1024` | 图片尺寸（暂不支持） |
| `quality` | string | 否 | `standard` | 图片质量（暂不支持） |
| `response_format` | string | 否 | `url` | 响应格式: `url`/`b64_json`/`base64` |
| `style` | string | 否 | - | 风格（暂不支持） |
| `stream` | boolean | 否 | `false` | 是否流式输出 |

#### 请求示例

**生成单张图片**:
```bash
curl -X POST http://localhost:8000/images/generations \
  -H "Content-Type: application/json" \
  -d '{
    "prompt": "一只在太空中的宇航员，数字艺术风格",
    "n": 1,
    "response_format": "url"
  }'
```

**生成多张图片**:
```bash
curl -X POST http://localhost:8000/images/generations \
  -H "Content-Type: application/json" \
  -d '{
    "prompt": "美丽的日落风景",
    "n": 4,
    "response_format": "b64_json"
  }'
```

**流式生成**:
```bash
curl -X POST http://localhost:8000/images/generations \
  -H "Content-Type: application/json" \
  -d '{
    "prompt": "赛博朋克城市夜景",
    "n": 1,
    "stream": true
  }'
```

#### 响应示例

**非流式响应**:
```json
{
  "created": 1234567890,
  "data": [
    {
      "url": "https://example.com/image1.jpg"
    },
    {
      "url": "https://example.com/image2.jpg"
    }
  ],
  "usage": {
    "total_tokens": 0,
    "input_tokens": 0,
    "output_tokens": 0
  }
}
```

**Base64 格式响应**:
```json
{
  "created": 1234567890,
  "data": [
    {
      "b64_json": "iVBORw0KGgoAAAANSUhEUgAA..."
    }
  ],
  "usage": {
    "total_tokens": 0,
    "input_tokens": 0,
    "output_tokens": 0
  }
}
```

**流式响应 (SSE)**:
```
event: image_generation.partial_image
data: {"index": 0, "b64_json": "iVBORw0KG..."}

event: image_generation.completed
data: {"created": 1234567890, "data": [...]}
```

---

### 2.2 编辑图片

**端点**: `POST /images/edits`

**描述**: 基于图片和文本描述进行图片编辑。

#### 请求参数

| 参数 | 类型 | 必填 | 默认值 | 描述 |
|------|------|------|--------|------|
| `prompt` | string | 是 | - | 编辑描述 |
| `image` | file | 是 | - | 待编辑图片文件 (最多 16 张) |
| `model` | string | 否 | `grok-imagine-1.0` | 模型名称 |
| `n` | integer | 否 | `1` | 生成数量 (1-10) |
| `size` | string | 否 | `1024x1024` | 图片尺寸（暂不支持） |
| `quality` | string | 否 | `standard` | 图片质量（暂不支持） |
| `response_format` | string | 否 | `url` | 响应格式 |
| `style` | string | 否 | - | 风格（暂不支持） |
| `stream` | boolean | 否 | `false` | 是否流式输出 |

#### 支持的图片格式
- PNG
- JPEG/JPG
- WebP

#### 文件大小限制
- 最大 50MB

#### 请求示例

```bash
curl -X POST http://localhost:8000/images/edits \
  -F "prompt=给图片添加一个蓝色的天空" \
  -F "image=@/path/to/image.jpg" \
  -F "n=1" \
  -F "response_format=url"
```

#### 响应示例

与图片生成 API 相同。

---

## 3. 视频任务 API

### 3.1 创建视频任务

**端点**: `POST /v1/video/tasks`

**描述**: 创建异步视频生成任务。

#### 请求参数

| 参数 | 类型 | 必填 | 默认值 | 描述 |
|------|------|------|--------|------|
| `model` | string | 是 | - | 模型名称 |
| `prompt` | string | 是 | - | 视频描述提示词 |
| `aspect_ratio` | string | 否 | `3:2` | 视频比例: `2:3`/`3:2`/`1:1`/`9:16`/`16:9` |
| `video_length` | integer | 否 | `6` | 视频时长(秒): `6` 或 `10` |
| `resolution` | string | 否 | `480p` | 视频分辨率: `480p`/`720p` |
| `preset` | string | 否 | `normal` | 风格预设: `fun`/`normal`/`spicy`/`custom` |
| `image_url` | string | 否 | - | 图片URL（用于图片转视频） |

#### 请求示例

**文本生成视频**:
```bash
curl -X POST http://localhost:8000/v1/video/tasks \
  -H "Content-Type: application/json" \
  -d '{
    "model": "grok-imagine-1.0-video",
    "prompt": "一只海豚在海洋中跳跃",
    "aspect_ratio": "16:9",
    "video_length": 6,
    "resolution": "480p",
    "preset": "normal"
  }'
```

**图片转视频**:
```bash
curl -X POST http://localhost:8000/v1/video/tasks \
  -H "Content-Type: application/json" \
  -d '{
    "model": "grok-imagine-1.0-video",
    "prompt": "让图片动起来",
    "image_url": "https://example.com/image.jpg",
    "aspect_ratio": "1:1",
    "video_length": 6
  }'
```

#### 响应示例

```json
{
  "status": "success",
  "task_id": "task_abc123",
  "message": "视频生成任务已提交"
}
```

---

### 3.2 查询任务状态

**端点**: `GET /v1/video/tasks/{task_id}`

**描述**: 查询指定任务的状态和结果。

#### 路径参数

| 参数 | 类型 | 必填 | 描述 |
|------|------|------|------|
| `task_id` | string | 是 | 任务 ID |

#### 请求示例

```bash
curl http://localhost:8000/v1/video/tasks/task_abc123
```

#### 响应示例

```json
{
  "task_id": "task_abc123",
  "status": "completed",
  "progress": 100,
  "prompt": "一只海豚在海洋中跳跃",
  "video_url": "https://example.com/video.mp4",
  "created_at": "2026-02-06T12:00:00Z",
  "started_at": "2026-02-06T12:00:01Z",
  "completed_at": "2026-02-06T12:01:30Z",
  "message": "视频生成完成"
}
```

#### 任务状态

| 状态 | 描述 |
|------|------|
| `pending` | 等待中 |
| `running` | 生成中 |
| `completed` | 已完成 |
| `failed` | 失败 |
| `cancelled` | 已取消 |

---

### 3.3 流式获取任务进度

**端点**: `GET /v1/video/tasks/{task_id}/stream`

**描述**: 通过 SSE 实时获取视频生成进度。

#### 请求示例

```bash
curl http://localhost:8000/v1/video/tasks/task_abc123/stream
```

#### 响应示例 (SSE)

```
data: {"type":"snapshot","status":"running","progress":45}

data: {"type":"progress","progress":50}

data: {"type":"progress","progress":75}

data: {"type":"completed","status":"completed","progress":100,"video_url":"https://example.com/video.mp4"}
```

---

### 3.4 取消任务

**端点**: `DELETE /v1/video/tasks/{task_id}`

**描述**: 取消正在进行的视频生成任务。

#### 请求示例

```bash
curl -X DELETE http://localhost:8000/v1/video/tasks/task_abc123
```

#### 响应示例

```json
{
  "status": "success",
  "message": "任务已取消"
}
```

---

### 3.5 批量删除任务

**端点**: `DELETE /v1/video/tasks`

**描述**: 批量删除指定的视频任务。

#### 请求参数

```json
{
  "task_ids": ["task_abc123", "task_def456"]
}
```

#### 请求示例

```bash
curl -X DELETE http://localhost:8000/v1/video/tasks \
  -H "Content-Type: application/json" \
  -d '{
    "task_ids": ["task_abc123", "task_def456"]
  }'
```

#### 响应示例

```json
{
  "status": "success",
  "count": 2,
  "message": "已删除 2 个任务"
}
```

---

### 3.6 按状态删除任务

**端点**: `DELETE /v1/video/tasks/status/{status}`

**描述**: 删除指定状态的所有视频任务。

#### 路径参数

| 参数 | 类型 | 必填 | 描述 |
|------|------|------|------|
| `status` | string | 是 | 任务状态: `pending`/`running`/`completed`/`failed`/`cancelled` |

#### 请求示例

```bash
curl -X DELETE http://localhost:8000/v1/video/tasks/status/failed
```

#### 响应示例

```json
{
  "status": "success",
  "count": 5,
  "message": "已删除 5 个 failed 任务"
}
```

---

### 3.7 清除所有任务

**端点**: `DELETE /v1/video/tasks/all`

**描述**: 清除所有视频任务。

#### 请求示例

```bash
curl -X DELETE http://localhost:8000/v1/video/tasks/all
```

#### 响应示例

```json
{
  "status": "success",
  "count": 10,
  "message": "已清除所有 10 个任务"
}
```

---

### 3.8 列出所有任务

**端点**: `GET /v1/video/tasks`

**描述**: 获取所有视频任务列表，可按状态筛选。

#### 查询参数

| 参数 | 类型 | 必填 | 描述 |
|------|------|------|------|
| `status` | string | 否 | 任务状态筛选 |

#### 请求示例

**获取所有任务**:
```bash
curl http://localhost:8000/v1/video/tasks
```

**按状态筛选**:
```bash
curl http://localhost:8000/v1/video/tasks?status=completed
```

#### 响应示例

```json
{
  "tasks": [
    {
      "task_id": "task_abc123",
      "status": "completed",
      "progress": 100,
      "prompt": "一只海豚在海洋中跳跃",
      "video_url": "https://example.com/video.mp4",
      "created_at": "2026-02-06T12:00:00Z",
      "started_at": "2026-02-06T12:00:01Z",
      "completed_at": "2026-02-06T12:01:30Z",
      "message": "视频生成完成"
    },
    {
      "task_id": "task_def456",
      "status": "running",
      "progress": 45,
      "prompt": "一只猫在花园里玩耍",
      "created_at": "2026-02-06T12:02:00Z",
      "started_at": "2026-02-06T12:02:01Z",
      "message": "视频生成中..."
    }
  ]
}
```

---

### 3.9 上传图片

**端点**: `POST /v1/video/upload`

**描述**: 上传图片到 Grok 服务器，用于图片转视频。

#### 请求参数

| 参数 | 类型 | 必填 | 描述 |
|------|------|------|------|
| `file` | file | 是 | 图片文件 |

#### 请求示例

```bash
curl -X POST http://localhost:8000/v1/video/upload \
  -F "file=@/path/to/image.jpg"
```

#### 响应示例

```json
{
  "file_id": "file_xyz789",
  "file_uri": "uploads/abc123/image.jpg",
  "image_url": "https://assets.grok.com/uploads/abc123/image.jpg"
}
```

---

## 4. 错误处理

### 4.1 错误响应格式

所有 API 在出错时返回统一的错误格式：

```json
{
  "error": {
    "message": "错误描述",
    "type": "错误类型",
    "param": "参数名",
    "code": "错误码"
  }
}
```

### 4.2 HTTP 状态码

| 状态码 | 描述 |
|--------|------|
| `200` | 成功 |
| `400` | 请求参数错误 |
| `404` | 资源不存在 |
| `429` | 请求频率超限 |
| `500` | 服务器内部错误 |

### 4.3 常见错误

#### 参数验证错误
```json
{
  "error": {
    "message": "Prompt cannot be empty",
    "type": "invalid_request_error",
    "param": "prompt",
    "code": "empty_prompt"
  }
}
```

#### 模型不存在
```json
{
  "error": {
    "message": "The model `invalid-model` does not exist or you do not have access to it.",
    "type": "invalid_request_error",
    "param": "model",
    "code": "model_not_found"
  }
}
```

#### 任务不存在
```json
{
  "detail": "任务不存在"
}
```

#### 无可用 Token
```json
{
  "error": {
    "message": "No available tokens. Please try again later.",
    "type": "rate_limit_error",
    "code": "rate_limit_exceeded"
  }
}
```

---

## 5. Python 示例代码

### 5.1 聊天补全

```python
import requests

def chat_completion(prompt, model="grok-2"):
    url = "http://localhost:8000/chat/completions"
    headers = {"Content-Type": "application/json"}
    data = {
        "model": model,
        "messages": [{"role": "user", "content": prompt}]
    }
    
    response = requests.post(url, json=data, headers=headers)
    return response.json()

result = chat_completion("你好，请介绍一下你自己")
print(result["choices"][0]["message"]["content"])
```

### 5.2 图片生成

```python
import requests

def generate_image(prompt, n=1, response_format="url"):
    url = "http://localhost:8000/images/generations"
    headers = {"Content-Type": "application/json"}
    data = {
        "prompt": prompt,
        "n": n,
        "response_format": response_format
    }
    
    response = requests.post(url, json=data, headers=headers)
    return response.json()

result = generate_image("一只在太空中的宇航员", n=2)
for image in result["data"]:
    print(image["url"])
```

### 5.3 视频任务

```python
import requests
import time

def create_video_task(prompt):
    url = "http://localhost:8000/v1/video/tasks"
    headers = {"Content-Type": "application/json"}
    data = {
        "model": "grok-imagine-1.0-video",
        "prompt": prompt,
        "aspect_ratio": "16:9",
        "video_length": 6,
        "resolution": "480p"
    }
    
    response = requests.post(url, json=data, headers=headers)
    return response.json()["task_id"]

def get_task_status(task_id):
    url = f"http://localhost:8000/v1/video/tasks/{task_id}"
    response = requests.get(url)
    return response.json()

task_id = create_video_task("一只海豚在海洋中跳跃")
print(f"任务 ID: {task_id}")

while True:
    status = get_task_status(task_id)
    print(f"状态: {status['status']}, 进度: {status['progress']}%")
    
    if status["status"] == "completed":
        print(f"视频 URL: {status['video_url']}")
        break
    elif status["status"] == "failed":
        print(f"错误: {status.get('message', '未知错误')}")
        break
    
    time.sleep(2)
```

### 5.4 流式响应

```python
import requests

def stream_chat_completion(prompt):
    url = "http://localhost:8000/chat/completions"
    headers = {"Content-Type": "application/json"}
    data = {
        "model": "grok-2",
        "messages": [{"role": "user", "content": prompt}],
        "stream": True
    }
    
    response = requests.post(url, json=data, headers=headers, stream=True)
    
    for line in response.iter_lines():
        if line:
            line = line.decode('utf-8')
            if line.startswith('data: '):
                data_str = line[6:]
                if data_str == '[DONE]':
                    break
                print(data_str, end='')

stream_chat_completion("写一首关于春天的诗")
```

---

## 6. JavaScript 示例代码

### 6.1 聊天补全

```javascript
async function chatCompletion(prompt, model = "grok-2") {
  const response = await fetch("http://localhost:8000/chat/completions", {
    method: "POST",
    headers: {
      "Content-Type": "application/json"
    },
    body: JSON.stringify({
      model: model,
      messages: [{ role: "user", content: prompt }]
    })
  });
  
  const data = await response.json();
  return data.choices[0].message.content;
}

chatCompletion("你好，请介绍一下你自己")
  .then(content => console.log(content));
```

### 6.2 图片生成

```javascript
async function generateImage(prompt, n = 1) {
  const response = await fetch("http://localhost:8000/images/generations", {
    method: "POST",
    headers: {
      "Content-Type": "application/json"
    },
    body: JSON.stringify({
      prompt: prompt,
      n: n,
      response_format: "url"
    })
  });
  
  const data = await response.json();
  return data.data;
}

generateImage("一只在太空中的宇航员", 2)
  .then(images => images.forEach(img => console.log(img.url)));
```

### 6.3 视频任务

```javascript
async function createVideoTask(prompt) {
  const response = await fetch("http://localhost:8000/v1/video/tasks", {
    method: "POST",
    headers: {
      "Content-Type": "application/json"
    },
    body: JSON.stringify({
      model: "grok-imagine-1.0-video",
      prompt: prompt,
      aspect_ratio: "16:9",
      video_length: 6,
      resolution: "480p"
    })
  });
  
  const data = await response.json();
  return data.task_id;
}

async function getTaskStatus(taskId) {
  const response = await fetch(`http://localhost:8000/v1/video/tasks/${taskId}`);
  return await response.json();
}

async function waitForVideo(taskId) {
  while (true) {
    const status = await getTaskStatus(taskId);
    console.log(`状态: ${status.status}, 进度: ${status.progress}%`);
    
    if (status.status === "completed") {
      console.log(`视频 URL: ${status.video_url}`);
      break;
    } else if (status.status === "failed") {
      console.log(`错误: ${status.message || "未知错误"}`);
      break;
    }
    
    await new Promise(resolve => setTimeout(resolve, 2000));
  }
}

createVideoTask("一只海豚在海洋中跳跃")
  .then(taskId => waitForVideo(taskId));
```

---

## 7. 注意事项

### 7.1 速率限制
- 当前版本无硬性速率限制
- Token 池耗尽时会返回 429 错误
- 建议合理控制请求频率

### 7.2 超时设置
- 聊天 API: 建议设置 60 秒超时
- 图片生成: 建议设置 120 秒超时
- 视频任务: 异步处理，无需设置长超时

### 7.3 流式响应
- 流式响应使用 SSE (Server-Sent Events) 格式
- 客户端需要处理 SSE 事件流
- 建议使用支持 SSE 的 HTTP 客户端

### 7.4 文件上传
- 图片文件最大 50MB
- 支持格式: PNG, JPEG, WebP
- 建议在上传前压缩图片

### 7.5 视频生成
- 视频生成是异步任务
- 建议使用 SSE 流式接口实时获取进度
- 任务完成后视频 URL 有效期为 24 小时

---

## 8. 更新日志

### v1.0.0 (2026-02-06)
- 初始版本发布
- 支持聊天补全 API
- 支持图片生成/编辑 API
- 支持视频任务管理 API
- 兼容 OpenAI API 格式

---

## 9. 技术支持

如有问题，请访问:
- GitHub Issues: https://github.com/chenyme/grok2api/issues
- 项目主页: https://github.com/chenyme/grok2api
