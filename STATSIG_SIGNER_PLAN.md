# Grok `x-statsig-id` 签名机方案 — 发现记录与开发计划

> 本文档记录 grok2api 出现 403 的根因排查、对 grok `x-statsig-id` 反爬签名的逆向分析、已实测验证的关键事实，以及把"签名微服务"接入本项目的完整改动计划。
>
> 目标读者：接手继续开发的人。读完本文应能不依赖此前对话、直接动手实现。

---

## 0. TL;DR（一句话版）

grok2api 现在所有聊天请求被 grok 上游 **403**，根因是请求头 `x-statsig-id` 发的是**老版本的"出错降级假值"**，已被 grok 新版反爬严格校验拒绝。真签名只能由 grok 自己的混淆 JS（依赖浏览器 DOM 指纹 + 时间戳）算出，无法用 Python 离线复刻。

**解决方案**：搭一个常驻的无头浏览器"签名机"容器，用 grok 自己的 JS 实时算签名，对内暴露 `POST /sign`；grok2api 发请求前来要签名。已实测：**一台签名机生成的签名可被全部账号复用，各扣各自额度，能把 403 打成 200。**

---

## 1. 403 根因

- 报错日志：`chat stream upstream failed: ... status=403 body=-`（空 body，典型反爬拦截，非业务错误）。
- 上游端点：`POST https://grok.com/rest/app-chat/conversations/new`。
- 决定性实验：**同一个有效 token**，在真实浏览器里由 grok 自己发 → **200**；自己手写 fetch（不带真签名）→ **403**。
- 结论：token、账号、Cloudflare 都没问题。**唯一差异是 `x-statsig-id` 请求头**。
  - 真实浏览器（200）：`x-statsig-id` 是 90+ 字符的加密签名，如 `XGr5G8ThxrAZ...`。
  - 本项目（403）：写死的 `btoa("e:TypeError: Cannot read properties of undefined (reading 'childNodes')")`，是 grok **早期版本的降级假值**（新版降级前缀已从 `e:` 改成 `x1:`）。

> 相关代码：[`app/dataplane/proxy/adapters/headers.py`](app/dataplane/proxy/adapters/headers.py) 的 `_statsig_id()`（约 L67），返回写死的 base64 假值。

---

## 2. 逆向分析：签名怎么生成的

### 2.1 调用结构（已还原）

grok 前端用 **Turbopack** 打包（全局 `globalThis.TURBOPACK`，非标准 webpack）。签名逻辑位于一个 chunk（当前部署文件名 `052qjt1__zlid.js`，**文件名和模块号会随 grok 发版变化**）里，还原后：

```js
// fetch 中间件：每个 grok API 请求发出前都会跑
let lH = async e => {
  let t, n = uuid_v4();                 // x-xai-request-id = 随机 uuid
  try {
    t = await lK(
      new URL(e.url).pathname.split("?")[0].trim(),  // 输入1：请求路径（去 query）
      e.init.method ?? ""                            // 输入2：HTTP 方法（如 "POST"）
    );
  } catch (e) {
    t = btoa(`x1:${e}`);                // 出错降级 → 这就是假值的来源
  }
  headers.set("x-xai-request-id", n);
  headers.set("x-statsig-id", t);       // 设置到请求头
};

// 异步加载签名模块（当前模块号 4629918），调 default() 得到签名函数
async function lK(n, i) {
  let a = await (e.A(4629918).then(e => e.default()));  // e = Turbopack require
  return await a(n, i);                 // a(pathname, method) = 真签名
}
```

- `window.fetch` **没有**被 grok 接管 —— 自己调 `fetch` 不会经过 `lH`，所以拿不到签名。必须拿到 `lK` 内部那个签名函数。

### 2.2 算法本质（已 dump 源码分析）

签名函数 `signer(path, method)`（完整混淆源码见 `docs/grok_signer_factory.dump.js`）干这几件事：

1. 取**当前秒级时间戳**（带固定偏移 `I = 0x644f6370`）拼进输入；
2. 算一份**浏览器 DOM / Canvas 指纹**：创建 DOM 元素、读 `childNodes`、跑 Web Animation、canvas —— `childNodes` 报错就来自这；指纹算一次后缓存在闭包变量 `j` / `A` 里；
3. 把 `method + "!" + path + "!" + 时间` 做 **SHA-256**（`crypto.subtle.digest`），混入那份指纹；
4. **base64** 输出（长度约 94）。

**两个硬约束**：
- 含**时间戳** → 签名有时效，不能永久缓存；
- 绑**真实浏览器 DOM** → 纯移植到 Python/Node **不可行**，必须在真实浏览器页面里跑。

---

## 3. 已实测验证的关键事实（带数据）

| 验证项 | 方法 | 结果 | 意义 |
|--------|------|------|------|
| token 可用 | 注入 sso cookie 打开 grok | 正常登录、能聊天 | 账号没问题 |
| 自己 fetch 不签名 | 页面内 fetch `conversations/new` 不带签名 | **403** | 签名是必需的 |
| 签名能提取 | route 注入暴露 `window.__grokSigner` | 拿到函数 | 提取可行 |
| 签名有效 | 用提取的签名手动发 `conversations/new` | **200** | 闭环成功 |
| 签名含时间戳 | 同 path 连续签两次 | 两次不同 | 有时效 |
| **签名可复用** | 同一个签名连发 3 次 | **全 200** | 时间窗口内可复用 → 可缓存 |
| **跨账号通用** | 账号 A 的签名 + 账号 B 的 Cookie | **200** | 一台签名机服务全账号 |
| 对照：无签名 | 账号 B 的 Cookie + 不带签名 | **403** | 反证签名确实起作用 |

**额度归属结论**：grok 按请求 **Cookie 里的 sso token** 认身份、扣额度；`x-statsig-id` 是**不记名反爬门票**，不含账号信息。所以一台签名机（用任一账号登录）出的签名，全部账号的请求都能用，**各扣各自 Cookie 账号的额度，互不串扣**；签名机本身不消耗聊天额度。

---

## 4. 签名提取方法（核心技术）

用 Playwright 的网络拦截，改写含签名逻辑的 chunk，把 grok **实际使用的** signer 实例暴露到 `window`。

**为什么暴露"实例"而非"工厂"**：签名函数有个 DOM 指纹缓存变量 `j`。grok 自己调用时会初始化它、之后走缓存不再碰 DOM；若自己 `factory()` 新建实例则缓存是空的，又去碰 DOM 就触发 `childNodes` 报错。必须复用 grok 已初始化好的那个实例。

```js
// 当前命中字符串（会随 grok 发版变化，生产代码必须用下面的健壮正则）
const needle = "e.A(4629918).then(e=>t(e.default()))";
const patched = "e.A(4629918).then(e=>{let s=e.default();try{window.__grokSigner=s;}catch(_){}return t(s)})";

// 健壮版：不写死模块号/文件名，遍历所有 chunk 用正则匹配
//   匹配 .A(<数字>).then(<X>=><Y>(<X>.default()))
const RE = /\.A\((\d+)\)\.then\((\w+)=>(\w+)\(\2\.default\(\)\)\)/;
// 替换为：
//   .A($1).then($2=>{let __s=$2.default();try{window.__grokSigner=__s}catch(e){};return $3(__s)})
```

**注入要点**：
- route 拦截 `**/_next/static/chunks/*.js`，对每个 chunk body 跑正则；命中则 replace、`route.fulfill`，否则原样放行。
- `default()` 只能调用一次（存的实例 = grok 用的实例）。
- 必须用**全新干净的 browser context**（`addInitScript` 会累积污染，导致 app 崩溃 / 发消息失败）。

**signer 初始化**：页面加载后，grok 的启动请求会触发 `lK` → 首次调用 signer → 初始化 `j` 缓存。签名机就绪判定 = 轮询 `window.__grokSigner` 出现 **且** 自检签名成功（不报 `childNodes`）。若长时间自检失败，主动发一条 temporary 消息触发初始化（**待验证：grok 启动请求是否足以触发，还是必须主动发消息**）。

---

## 5. 整体架构

```
┌─────────────┐   POST /sign {path, method}   ┌──────────────────────────┐
│  grok2api   │ ────────────────────────────▶ │  statsig-signer (新)     │
│             │ ◀──────────────────────────── │  Node + Playwright       │
│ _statsig_id │     { statsig: "<sig>" }      │  常驻无头 grok 页面        │
└─────────────┘                                │  window.__grokSigner     │
      │  带真签名发请求                          └──────────────────────────┘
      ▼                                                  │ 走项目同款代理出网
┌─────────────┐                                          ▼
│  grok.com   │ ◀──────────────── 200 ────────────  (proxy.egress.proxy_url)
└─────────────┘
```

- 两个容器同处 `grok2api_default` docker 网络，grok2api 用服务名 `http://statsig-signer:PORT/sign` 访问。
- 签名机走**项目页面配置的代理**（见 §7）访问 grok.com。

---

## 6. grok2api 侧改动清单

### 6.1 配置：[`config.defaults.toml`](config.defaults.toml) 新增段

```toml
# ==================== Statsig 签名 ====================
[statsig]
# 签名服务地址；留空 = 回退到内置假值（旧行为）
signer_url = ""
# 调用签名服务的超时（秒）
timeout = 5
```

- 环境变量覆盖（机制见 [`app/platform/config/snapshot.py`](app/platform/config/snapshot.py) `_apply_env`，`GROK_<SECTION>_<KEY>` → `section.key`）：
  - `GROK_STATSIG_SIGNER_URL` → `statsig.signer_url`
  - `GROK_STATSIG_TIMEOUT` → `statsig.timeout`

### 6.2 核心：[`app/dataplane/proxy/adapters/headers.py`](app/dataplane/proxy/adapters/headers.py)

1. `_statsig_id()` 改为接收 `path` / `method`：
   ```python
   def _statsig_id(path: str = "", method: str = "POST") -> str:
       cfg = get_config()
       signer_url = cfg.get_str("statsig.signer_url", "").strip()
       if signer_url:
           sig = _fetch_remote_statsig(signer_url, path, method, cfg)
           if sig:
               return sig
           # 远程失败 → 落回旧的假值逻辑（降级不阻断）
       # ... 保留原有 dynamic_statsig / 写死假值逻辑作为 fallback
   ```
2. 新增 `_fetch_remote_statsig(signer_url, path, method, cfg)`：**同步** HTTP POST（用标准库 `urllib`，不引新依赖），短超时；成功返回签名字符串，失败返回 `None`。
   - 同步调用会短暂阻塞 event loop（~毫秒级，签名机本地 + 缓存命中快），对本项目并发量可接受。若后续要彻底无阻塞，再考虑异步化（见 §9 风险）。
3. `build_http_headers(...)` 增加参数 `url: str | None = None, method: str = "POST"`，内部 `path = urlparse(url).path if url else ""`，把 `path, method` 传给 `_statsig_id`。

### 6.3 调用点：给 `build_http_headers` 传 `url` + `method`

`build_http_headers` 共 8 处调用，都在能拿到目标 url 的上下文里（transport 函数首参就是 `url`）。逐一补 `url=url`（GET/DELETE 端点补 `method="GET"`/`"DELETE"`）：

| 文件 | 行（约） | method |
|------|---------|--------|
| [`app/dataplane/reverse/transport/http.py`](app/dataplane/reverse/transport/http.py) | post_stream L31 / post_json L104 | POST |
| 同上 | get_json L143 | GET |
| 同上 | delete_json L190 | DELETE |
| 同上 | get_bytes_stream L242 | GET |
| [`app/dataplane/reverse/transport/grpc_web.py`](app/dataplane/reverse/transport/grpc_web.py) | L52 | POST |
| [`app/dataplane/reverse/transport/asset_upload.py`](app/dataplane/reverse/transport/asset_upload.py) | L128 / L189 | POST |
| [`app/products/openai/images.py`](app/products/openai/images.py) | L909 / L951 | POST |
| [`app/products/openai/video.py`](app/products/openai/video.py) | L330 | POST |
| [`app/products/openai/chat.py`](app/products/openai/chat.py) | L406 | POST |

> 最关键的是 chat 的 `conversations/new`（L406）—— 这是当前 403 的端点。其余端点保险起见一并补全（部分端点如 rate-limits 实测不强制签名，但补了无害）。

### 6.4 TDD

`_fetch_remote_statsig` 可单测（mock signer_url 返回值 / 超时 / 失败回退）。签名机是 Node 服务，靠集成测试（启动后 curl `/sign` + 真实请求 200）验证。

---

## 7. 代理：签名机如何复用项目页面配置的代理

**结论：可以，但需要把代理喂给无头浏览器。**

- 项目代理存在 config（`proxy.egress.proxy_url`，页面配置写入 `data/config.toml`，运行时 `get_config()` 读取）。
- 签名机是独立容器，无法直接调用项目内部的 `get_config()`。两种喂法：
  1. **签名机挂载 `./data` 只读**，启动时自己解析 `data/config.toml` 取 `proxy.egress.proxy_url`，作为 Playwright `launch({ proxy: { server } })`。页面改代理后签名机需重启（或定期重读、变化则重启浏览器）。
  2. **docker-compose 里用环境变量传**：`PROXY_URL=${...}`，与 grok2api 的代理保持一致。简单但不会跟随页面动态改。
- 推荐：**方案 1 为主**（自动跟随项目配置）+ 方案 2 环境变量兜底覆盖。
- 注意：Playwright/Chromium 的 `proxy.server` 支持 `http://` 与 `socks5://`；项目代理是 `http://192.168.31.135:1089`，直接可用。

---

## 8. 签名机服务设计（`statsig-signer/`，新建目录）

**技术栈**：Node + Playwright（基础镜像 `mcr.microsoft.com/playwright:v1.xx-jammy`，自带 Chromium）。

**目录结构**（建议）：
```
statsig-signer/
  server.js          # HTTP 服务 + Playwright 驱动
  package.json
  Dockerfile
```

**server.js 关键逻辑**：
1. 启动 Playwright chromium（headless），`launch({ proxy })` 用项目代理。
2. 读取 sso token（来源见下），`newContext()` + `addCookies(sso / sso-rw)`。
3. `route` 拦截所有 chunk，用 §4 的健壮正则注入暴露 `window.__grokSigner`。
4. `goto("https://grok.com/")`，轮询直到 `window.__grokSigner` 就绪且自检签名成功；必要时主动发一条 temporary 消息初始化。
5. HTTP 接口 `POST /sign {path, method}` → `page.evaluate(([p,m]) => window.__grokSigner(p,m), [path,method])` → 返回 `{ statsig }`。
6. **缓存**：按 `path|method` 缓存签名，TTL 建议 30~60s（实测可复用，留时间窗口余量），降低 evaluate 频率。
7. **健壮性**：`/health` 健康检查；signer 失效 / 页面崩溃 / token 过期时自动重载页面、重试、必要时换 token；`restart: unless-stopped`。

**sso token 来源**：
- MVP：环境变量 `GROK_SSO_TOKEN` 传一个有效 token（用户有 4500 个，随便填一个）。失效需手动换。
- 增强：挂载 `./data/accounts.db`，启动时自动取一个 `status=active` 的 token，失效自动轮换下一个（需 Node sqlite 依赖）。

---

## 9. docker-compose 集成

- grok2api 服务从官方镜像改为**本地构建**（`build: .`），否则代码改动不生效：
  ```yaml
  grok2api:
    build: .            # 原为 image: ghcr.io/chenyme/grok2api:latest
    environment:
      GROK_STATSIG_SIGNER_URL: http://statsig-signer:3000/sign
    depends_on:
      - statsig-signer
  ```
- 新增签名机服务：
  ```yaml
  statsig-signer:
    build: ./statsig-signer
    environment:
      TZ: Asia/Shanghai
      GROK_SSO_TOKEN: ${GROK_SSO_TOKEN:-}
      PROXY_URL: ${STATSIG_PROXY_URL:-}     # 留空则签名机自己读 data/config.toml
    volumes:
      - ./data:/app/data:ro                 # 读 token / 代理配置
    restart: unless-stopped
  ```
- 部署：`docker compose up -d --build`。

---

## 10. 风险 / 待办 / 待决策

**待验证**：
- [ ] signer 的 `j` 缓存：grok 启动请求是否足以触发初始化，还是签名机必须主动发一条消息。
- [ ] 签名 TTL 上限：服务端时间窗口到底多宽（决定缓存 TTL，目前保守取 30~60s）。
- [ ] 同步 HTTP 调签名机对高并发 event loop 的实际影响（量级评估，必要时异步化）。

**风险**：
- **grok 改版脆性**（逆向方案固有）：模块号 `4629918`、chunk 文件名、`needle` 结构都可能变。已用健壮正则匹配缓解小改；大改 signer 结构时需更新注入逻辑。
- **签名机单点**：挂了所有请求 403 → 必须健康检查 + 自动重启 + 降级（远程失败时 headers.py 落回假值，至少不崩）。
- **token 过期**：签名机登录态失效 → 签名可能失败。需健康自检 + 自动换 token。

**待决策**：
- [ ] token 来源走环境变量（MVP）还是 accounts.db 自动轮换（增强）。
- [ ] 代理喂法：签名机自读 config.toml（推荐）还是纯环境变量。
- [ ] 是否给 grok2api 侧也加一层本地签名缓存进一步降延迟。

---

## 11. 环境信息（内网部署目标）

- 内网主机：31G 内存（可用 11G+）、4 核、Docker 26.1.4、CentOS 7。
- grok2api 当前：容器 `grok2api`，网络 `grok2api_default`，`./data`（accounts.db 4500+ 账号 / config.toml）+ `./logs` 挂载。
- 现网代理：`proxy.egress.mode=single_proxy`，`proxy_url=http://192.168.31.135:1089`。
- 参考资料：`docs/grok_signer_factory.dump.js`（逆向 dump 的签名函数完整混淆源码 + 注释）。
