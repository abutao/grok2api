# /admin/text 异步任务鉴权与请求规范调研报告

## 结论摘要
- /admin/text 页面提交的视频与图片异步任务由 /v1/admin/tasks/async 处理，必须提供有效的 app_key 才能成功提交。
- 请求体不包含 key 字段，鉴权通过 Authorization: Bearer <app_key> 传递。
- 缺失或无效 key 返回 401，错误体为 authentication_error + invalid_api_key。
- “过期”语义在本项目中不存在，过期等价于无效 key。

## 关联实现位置
- 后台鉴权：verify_app_key [auth.py](file:///f:/Code%20Learning/grok2api-main/app/core/auth.py#L83-L152)
- 管理端异步任务入口：/v1/admin/tasks/async [tasks.py](file:///f:/Code%20Learning/grok2api-main/app/api/v1/admin_api/tasks.py#L55-L88)
- 管理端页面提交逻辑：/admin/text [text.js](file:///f:/Code%20Learning/grok2api-main/app/static/admin/js/text.js#L294-L367)
- 管理端登录与本地存储：app_key 持久化 [admin-auth.js](file:///f:/Code%20Learning/grok2api-main/app/static/common/js/admin-auth.js#L105-L178)

## 请求参数规范（/v1/admin/tasks/async）

### 请求头
- Authorization: Bearer <app_key>（必填）

### 请求体结构
```json
{
  "type": "video|image",
  "payload": { ... }
}
```

### 视频创作 payload（来自 text.js 组装）
```json
{
  "model": "grok-imagine-1.0-video",
  "prompt": "string",
  "video_config": {
    "aspect_ratio": "3:2",
    "video_length": 6,
    "resolution_name": "480p",
    "preset": "normal"
  }
}
```

### 图片创作 payload（来自 text.js 组装）
```json
{
  "model": "grok-imagine-1.0",
  "prompt": "string",
  "size": "1024x1024",
  "n": 1,
  "response_format": "url"
}
```

### key 字段必填性结论
- 请求体不包含 key 字段；鉴权只通过 Authorization 头传入。
- /v1/admin/tasks/async 依赖 verify_app_key，app_key 未配置或无效会直接返回 401。

## 抓包/日志验证结果（本地实际请求）

### 图片任务
- valid key → 200
- missing key → 401 + Missing authentication token
- invalid key → 401 + Invalid authentication token
- empty key → 客户端拒绝（httpx 不允许 “Bearer ” 空值）

### 视频任务
- valid key → 200
- missing key → 401 + Missing authentication token
- invalid key → 401 + Invalid authentication token
- empty key → 客户端拒绝（httpx 不允许 “Bearer ” 空值）

### 权限不足（用 api_key 访问 admin）
- 401 + Invalid authentication token

## key 获取与配置步骤

### 申请渠道
- 本项目为本地/私有部署模型，app_key 为后台管理密码，直接由部署方在配置文件中设置。

### 权限范围
- app_key：仅管理端接口（/v1/admin/*）。
- api_key：面向对外业务接口（/v1/chat、/v1/images、/v1/video 等）。
- public_key：public 入口接口（/v1/public/*），需 public_enabled=true。

### 有效期与刷新机制
- app_key 无过期机制；修改后即生效，前端需重新登录。
- api_key/public_key 同样无过期机制；如需轮换，更新配置并重启或通过配置接口更新。

### 配置方式
- 配置文件：data/config.toml 中的 [app] 段（app_key/api_key/public_key）。
- 管理端登录：/admin/login 输入 app_key，存入 localStorage（grok2api_app_key）。
- 自动化脚本：Authorization 头中传入 Bearer <app_key>。

## 对比结论（有 key vs 无 key）

说明：接口未返回队列延迟与回调状态，本表以“提交响应耗时”和“是否可产生任务”替代；回调状态标记为 N/A。

| 场景 | 视频任务提交成功率 | 图片任务提交成功率 | 提交响应耗时 | 回调地址状态码 |
| --- | --- | --- | --- | --- |
| 有 key | 100% (1/1) | 100% (1/1) | 85ms / 311ms | N/A |
| 无 key | 0% (0/1) | 0% (0/1) | 26–43ms | N/A |

## 交付说明
- 测试脚本：tests/admin_text_auth_script.py
- 环境配置清单：docs/admin-text-env-checklist.md
