# 视频异步接口：`/tasks` 与当前 `/jobs` 的差别

## 你之前的风格（`/v1/video/tasks`）

典型设计一般是：

| 操作     | 方法 | URL 示例 |
|----------|------|----------|
| 提交任务 | POST | `POST /v1/video/tasks` |
| 查询任务 | GET  | `GET /v1/video/tasks/{task_id}` |
| 流式进度 | GET  | `GET /v1/video/tasks/{task_id}/stream`（若有） |

- **路径语义**：`tasks` 表示「任务」资源，REST 里常用来表示「可创建、可查询的一笔任务」。
- **ID 命名**：响应/路径里多为 `task_id`。
- **风格**：资源名是「任务」本身，和「生成」解耦，适合任务中心、工作流等场景。

---

## 当前实现（`/v1/video/jobs` + `generations/async`）

| 操作     | 方法 | 当前 URL |
|----------|------|----------|
| 提交任务 | POST | `POST /v1/video/generations/async` |
| 查询任务 | GET  | `GET /v1/video/jobs/{job_id}` |
| 流式进度 | GET  | `GET /v1/video/jobs/{job_id}/stream` |

- **路径语义**：  
  - 提交用 `generations/async`，强调「异步生成」动作。  
  - 查询用 `jobs`，和内部实现（video_jobs、job_id）一致。
- **ID 命名**：统一用 `job_id`。
- **风格**：更偏「生成 API + 任务查询」分离，和 OpenAI 的 `generations` 命名靠近。

---

## 主要差别对比

| 维度       | 之前 `/tasks` 风格           | 当前 `/jobs` + `generations/async` |
|------------|-----------------------------|-------------------------------------|
| 提交 URL   | `POST /v1/video/tasks`      | `POST /v1/video/generations/async`  |
| 查询 URL   | `GET /v1/video/tasks/{id}`  | `GET /v1/video/jobs/{job_id}`       |
| 资源名     | 任务（task）                | 生成（generations）+ 作业（job）    |
| ID 字段名  | 多为 `task_id`              | `job_id`                            |
| 语义       | 以「任务」为主线            | 以「生成 + 作业」为主线             |

功能上等价：都是「异步提交 → 用 ID 轮询或 SSE 查进度/结果」，只是路径和命名不同。

---

## 当前已做的兼容：两种 URL 均可使用

已增加 **tasks 风格别名**，与现有 jobs/generations 并存：

| 操作     | tasks 风格（兼容旧版）           | 当前 jobs 风格                    |
|----------|----------------------------------|-----------------------------------|
| 提交     | `POST /v1/video/tasks`          | `POST /v1/video/generations/async` |
| 查询     | `GET /v1/video/tasks/{task_id}` | `GET /v1/video/jobs/{job_id}`     |
| SSE 流   | `GET /v1/video/tasks/{task_id}/stream` | `GET /v1/video/jobs/{job_id}/stream` |

- 两套路径**共用同一套任务存储**，`task_id` 与 `job_id` 同值。
- 使用 `POST /v1/video/tasks` 时，响应中会同时返回 `task_id` 和 `job_id`；查询/stream 的响应里也会带 `task_id` 字段。
- 旧客户端可继续使用 `http://localhost:8000/v1/video/tasks`，新代码可任选其一。
