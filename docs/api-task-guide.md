# 外部调用：提交任务与查询任务

本文说明外部软件如何通过本项目 API **提交任务** 与 **查询任务**。项目里包含：

- **业务 API**（对话）：无“任务 ID”，直接请求→等响应或流式读。
- **图片/视频异步任务**：提交得 `job_id`，轮询或 SSE 查询进度与结果。
- **管理端批量任务**：先提交得 `task_id`，再通过 SSE 流查询进度/结果。

---

## 一、业务 API（对话 / 图像 / 模型列表）

用于对话、图像生成/编辑、模型列表等，**没有“任务 ID + 轮询”**，只有两种用法：

### 1. 同步调用（等完整响应）

发一次请求，一直等到完整响应返回。

```bash
# 对话
curl -X POST "http://localhost:8003/v1/chat/completions" \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer YOUR_API_KEY" \
  -d '{"model":"grok-4","messages":[{"role":"user","content":"你好"}],"stream":false}'

# 图像生成
curl -X POST "http://localhost:8003/v1/images/generations" \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer YOUR_API_KEY" \
  -d '{"model":"grok-imagine-1.0","prompt":"一只猫","n":1}'
```

`YOUR_API_KEY` 为配置项 `app.api_key`（在 `data/config.toml` 或环境变量）；若未配置则可不带 Authorization。

### 2. 流式调用（边收边处理）

请求里设 `"stream": true`，服务端用 SSE/流式 body 持续返回数据，客户端边收边处理。

```bash
curl -X POST "http://localhost:8003/v1/chat/completions" \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer YOUR_API_KEY" \
  -d '{"model":"grok-4","messages":[{"role":"user","content":"你好"}],"stream":true}'
```

---

## 二、管理端批量任务（提交任务 + 查询任务）

管理端部分操作是 **异步批量任务**：接口先返回 `task_id`，外部再通过 **SSE 流** 查询进度和结果。

### 认证

- 提交任务、取消任务：请求头 `Authorization: Bearer <api_key>`，其中 `<api_key>` 为配置项 `app.api_key`。
- 查询任务（SSE）：同上 Bearer，或使用查询参数 `?api_key=<api_key>`（例如在浏览器 EventSource 里用）。

若未配置 `app.api_key`，则这些接口不校验认证。

---

### 1. 提交任务（返回 task_id）

以下接口会**立即返回**，并在响应里带 `task_id`，用于后续查询/取消：

| 接口 | 方法 | 说明 | 请求体示例 |
|------|------|------|-------------|
| 批量刷新 Token 用量 | `POST /api/v1/admin/tokens/refresh/async` | 异步刷新，返回 task_id | `{"tokens":["token1","token2"]}` |
| 批量开启 NSFW | `POST /api/v1/admin/tokens/nsfw/enable/async` | 异步开启，返回 task_id | `{"tokens":["token1"]}` |
| 加载在线缓存详情 | `POST /api/v1/admin/cache/online/load/async` | 异步加载缓存，返回 task_id | `{"tokens":["token1"]}` |
| 清理在线缓存 | `POST /api/v1/admin/cache/online/clear/async` | 异步清理，返回 task_id | `{"tokens":["token1"]}` |

**示例：提交“批量刷新 Token”任务**

```bash
curl -X POST "http://localhost:8003/api/v1/admin/tokens/refresh/async" \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer YOUR_API_KEY" \
  -d '{"tokens":["your_grok_token1","your_grok_token2"]}'
```

**响应示例：**

```json
{
  "status": "success",
  "task_id": "a1b2c3d4e5f6...",
  "total": 2
}
```

记下 `task_id`，用于下一步“查询任务”。

---

### 2. 查询任务（SSE 流）

通过 **SSE** 连接拿到任务进度和最终结果，直到收到 `done` / `error` / `cancelled` 为止。

**接口：**

```http
GET /api/v1/admin/batch/{task_id}/stream
```

**认证（二选一）：**

- 请求头：`Authorization: Bearer <api_key>`
- 或查询参数：`?api_key=<api_key>`

**示例：**

```bash
# 使用 Bearer
curl -N "http://localhost:8003/api/v1/admin/batch/a1b2c3d4e5f6.../stream" \
  -H "Authorization: Bearer YOUR_API_KEY"

# 或使用 query
curl -N "http://localhost:8003/api/v1/admin/batch/a1b2c3d4e5f6.../stream?api_key=YOUR_API_KEY"
```

**SSE 事件类型：**

| type | 说明 |
|------|------|
| `snapshot` | 当前进度快照（total / processed / ok / fail 等） |
| `progress` | 每处理一条记录推送一次进度 |
| `done` | 任务正常结束，带 `result` |
| `error` | 任务失败，带 `error` |
| `cancelled` | 任务被取消 |

**事件数据示例：**

```text
data: {"type":"snapshot","task_id":"...","status":"running","total":10,"processed":0,"ok":0,"fail":0}
data: {"type":"progress","task_id":"...","total":10,"processed":1,"ok":1,"fail":0}
...
data: {"type":"done","task_id":"...","status":"done","result":{...}}
```

外部软件可：先 **POST 异步接口** 拿到 `task_id`，再 **GET .../stream** 用 SSE 消费进度和结果。

---

### 3. 取消任务

**接口：**

```http
POST /api/v1/admin/batch/{task_id}/cancel
```

**请求头：** `Authorization: Bearer <api_key>`

**示例：**

```bash
curl -X POST "http://localhost:8003/api/v1/admin/batch/a1b2c3d4e5f6.../cancel" \
  -H "Authorization: Bearer YOUR_API_KEY"
```

---

## 三、流程小结

- **业务 API（/v1/chat、/v1/images 等）**  
  - 同步：发 POST → 等完整 JSON 响应。  
  - 流式：发 POST（stream: true）→ 读流式 body/SSE。

- **管理端批量任务**  
  1. **提交**：POST 对应 `/api/v1/admin/.../async` 接口 → 响应里拿到 `task_id`。  
  2. **查询**：GET `/api/v1/admin/batch/{task_id}/stream`，用 SSE 接收进度和最终结果。  
  3. **取消**（可选）：POST `/api/v1/admin/batch/{task_id}/cancel`。

- **认证**  
  - 业务 API 与管理端 API 均使用同一配置项 `app.api_key`（Bearer）。  
  - 查询任务流除 Bearer 外，也可用 `?api_key=`。

若你希望增加“按 task_id 轮询状态”的 REST 接口（非 SSE），可以在现有 `get_task(task_id)` 上再包一层 GET 即可；当前官方只提供 SSE 一种查询方式。

---

## 四、图片生成异步任务（提交 + 查询结果）

与视频类似，图片生成也支持**异步提交**，再通过轮询或 SSE 查询结果。

### 1. 提交图片生成任务

**接口：** `POST /v1/images/generations/async`

**请求体：** 与 `POST /v1/images/generations` 一致（`prompt` 必填，可选 `model`、`n`、`size`、`response_format` 等；不要传 `stream: true`）。

**示例：**

```bash
curl -X POST "http://localhost:8003/v1/images/generations/async" \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer YOUR_API_KEY" \
  -d '{"prompt":"一只在太空的猫","n":1,"response_format":"url"}'
```

**响应示例：**

```json
{
  "job_id": "a1b2c3d4...",
  "status": "pending",
  "message": "Image generation started. Poll GET /v1/images/jobs/{job_id} or GET /v1/images/jobs/{job_id}/stream for result."
}
```

### 2. 查询任务（轮询）

**接口：** `GET /v1/images/jobs/{job_id}`

**响应示例（已完成）：**

```json
{
  "job_id": "a1b2c3d4...",
  "status": "completed",
  "progress": 100,
  "result": {
    "created": 1234567890,
    "data": [{"url": "https://your-host/..."}],
    "usage": {...}
  }
}
```

### 3. 查询任务（SSE 流）

**接口：** `GET /v1/images/jobs/{job_id}/stream`

通过 SSE 接收 `snapshot`、`progress`、`completed`、`failed` 等事件。

---

## 五、视频生成异步任务（提交 + 查询进度与结果）

外部软件可以**异步**提交视频生成任务，再通过轮询或 SSE 查询进度和结果。

### 1. 提交视频生成任务

**接口：** `POST /v1/video/generations/async`

**请求体：** 与 `POST /v1/chat/completions` 一致，且必须使用**视频模型**（如 `grok-imagine-1.0-video`）。需包含 `model`、`messages`，可选 `video_config`、`thinking`。

**示例：**

```bash
curl -X POST "http://localhost:8003/v1/video/generations/async" \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer YOUR_API_KEY" \
  -d '{
    "model": "grok-imagine-1.0-video",
    "messages": [{"role":"user","content":"一只猫在跑步"}],
    "video_config": {"aspect_ratio":"16:9","video_length":6}
  }'
```

**响应示例：**

```json
{
  "job_id": "a1b2c3d4e5f6...",
  "status": "pending",
  "message": "Video generation started. Poll GET /v1/video/jobs/{job_id} or connect to GET /v1/video/jobs/{job_id}/stream for progress."
}
```

### 2. 查询任务（轮询）

**接口：** `GET /v1/video/jobs/{job_id}`

**示例：**

```bash
curl "http://localhost:8003/v1/video/jobs/a1b2c3d4e5f6..." \
  -H "Authorization: Bearer YOUR_API_KEY"
```

**响应示例（进行中）：**

```json
{
  "job_id": "a1b2c3d4e5f6...",
  "status": "running",
  "progress": 45,
  "created_at": 1234567890.0
}
```

**响应示例（已完成）：**

```json
{
  "job_id": "a1b2c3d4e5f6...",
  "status": "completed",
  "progress": 100,
  "created_at": 1234567890.0,
  "completed_at": 1234567895.0,
  "result": {
    "content": "https://your-host/video/xxx.mp4",
    "video_url": "https://your-host/video/xxx.mp4",
    "thumbnail_url": "https://your-host/..."
  }
}
```

**响应示例（失败）：**

```json
{
  "job_id": "a1b2c3d4e5f6...",
  "status": "failed",
  "error": "错误信息",
  "completed_at": 1234567895.0
}
```

### 3. 查询任务（SSE 流）

**接口：** `GET /v1/video/jobs/{job_id}/stream`

通过 SSE 持续接收进度与最终结果，事件类型包括：

- `snapshot`：当前状态快照
- `progress`：进度更新（含 `progress` 0–100）
- `completed`：任务完成，含 `result`
- `failed`：任务失败，含 `error`

**示例：**

```bash
curl -N "http://localhost:8003/v1/video/jobs/a1b2c3d4e5f6.../stream" \
  -H "Authorization: Bearer YOUR_API_KEY"
```

### 4. 流程小结（视频异步）

1. **提交**：`POST /v1/video/generations/async` → 响应中拿到 `job_id`
2. **查询**：轮询 `GET /v1/video/jobs/{job_id}` 或连接 `GET /v1/video/jobs/{job_id}/stream` 收 SSE
3. 认证与业务 API 一致，使用 `Authorization: Bearer <api_key>`（配置项 `app.api_key`）

---

## 六、图片与视频异步汇总

| 能力       | 提交接口                          | 轮询接口                    | SSE 接口                         |
|------------|-----------------------------------|-----------------------------|----------------------------------|
| 图片生成   | `POST /v1/images/generations/async` | `GET /v1/images/jobs/{job_id}` | `GET /v1/images/jobs/{job_id}/stream` |
| 视频生成   | `POST /v1/video/generations/async` | `GET /v1/video/jobs/{job_id}` | `GET /v1/video/jobs/{job_id}/stream`  |

外部软件可统一采用：**异步提交 → 拿到 job_id → 轮询或 SSE 查询进度与结果**。
