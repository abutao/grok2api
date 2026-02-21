# /admin/text 环境配置清单

## 必需项
- 服务启动在 http://localhost:8000
- data/config.toml 的 [app] 段已设置 app_key
- 管理端登录后 localStorage 包含 grok2api_app_key

## 推荐项
- [app].api_key 配置对外接口调用所需 key
- [app].public_key 与 public_enabled 配置 public 入口

## Key 注入方式
- 前端管理端：/admin/login 输入 app_key，自动写入 localStorage
- 接口调用：Authorization: Bearer <app_key>

## 脚本运行方式
- 直接读取 data/config.toml
- 可用环境变量覆盖：
  - GROK2API_BASE_URL
  - GROK2API_APP_KEY
  - GROK2API_API_KEY
