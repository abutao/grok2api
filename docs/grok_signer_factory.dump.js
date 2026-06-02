/* ===========================================================================
 * grok x-statsig-id 签名函数 —— 逆向 dump 与解读
 * ===========================================================================
 *
 * 来源：grok.com 前端 chunk（当前部署 052qjt1__zlid.js，模块号 4629918）。
 * 通过 Playwright route 注入把 grok 实际使用的 signer 实例暴露到 window 后 dump。
 * 文件名 / 模块号会随 grok 发版变化；本文件仅作算法参考，不是可运行代码。
 *
 * 调用契约：signer(path, method) -> Promise<string>
 *   path   = new URL(reqUrl).pathname.split("?")[0].trim()  例 "/rest/app-chat/conversations/new"
 *   method = "POST" / "GET" / ...
 *   返回   = base64 字符串（长度约 94），即 x-statsig-id 的值
 *
 * 混淆手段：字符串数组解码函数 t(idx,key) + 控制流平坦化 + 大量死代码分支。
 * 下面的解读基于对未混淆语义的还原，变量名沿用 dump 中的单字母名。
 * ===========================================================================
 *
 * ── factory 头部关键定义（摘录） ──────────────────────────────────────────
 *
 *   [e, u] = [document, window]
 *
 *   // base64 输出（去掉 = padding）
 *   h = W => btoa( q(W).map(c => String.fromCharCode(c)).join("") ).replace(/=/g, "")
 *
 *   // crypto.subtle.digest("SHA-256", N(W))   —— l = crypto.subtle
 *   v = W => l.digest("SHA-256", N(W))
 *
 *   // N：字符串 -> Uint8Array（TextEncoder）；i = Uint8Array, f = TextEncoder
 *   N = W => typeof W === "string" ? new f().encode(W) : W
 *
 *   // G：读取页面 <script> 标签的 content 属性，作为 DOM 指纹种子之一
 *   G = () => new i(atob(H(k(document.querySelectorAll("script")[0], "content")) ...))
 *
 *   // s：创建一个 DOM 元素并挂到 documentElement，参与指纹计算
 *   s = () => { let t = document.createElement(...); document.documentElement.append(t); ... }
 *
 *   // Q：遍历节点读取属性（这一族操作里访问 .childNodes，裸调用且 DOM 状态不对时即抛
 *   //    "Cannot read properties of undefined (reading 'childNodes')" —— 即降级假值来源）
 *
 *   // 时间相关：a() 取时间，I = 0x644f6370 是固定偏移；e = K(floor((now()/1000 + I*1000)/1000))
 *   I = 0x644f6370
 *
 *   // Z(d)：根据 DOM 指纹 d 生成 canvas / WebAnimation 指纹，结果缓存到闭包变量 A，
 *   //       并记 j = d；下次同 d 直接返回缓存 A，不再触碰 DOM（这是"复用实例"能成功的原因）
 *
 * ── signer 主体（return 的 async 函数，精确 dump） ─────────────────────────
 *
 *   async (W, n) => {                       // W = path, n = method
 *     let e = K( floor( (a() + I*1000) / 1000 ) );      // 秒级时间戳（含偏移）
 *     let u = new Uint8Array(new TextEncoder([e]).encode...);
 *     let d = j || G();                     // DOM 指纹（缓存优先）
 *     let f = Z(d);                         // canvas/animation 指纹
 *     return h(                             // base64 输出
 *       new Uint8Array([
 *         (w() & 256),                      // 版本/标志字节
 *         ...q(d),                          // DOM 指纹字节
 *         ...q(u),                          // 时间戳字节
 *         ...D( q( new Uint8Array(
 *               await v(                    // ★ SHA-256(
 *                 [n, W, e].join("!"),      //     method!path!timestamp
 *                 ...                        //   ) 再混入 f 指纹
 *               )
 *             ).slice(_) ) )
 *       ].map(b))
 *     );
 *   }
 *
 * ── 一句话 ────────────────────────────────────────────────────────────────
 *   signature = base64( [flag, DOM指纹, 时间戳, SHA256(method!path!时间, 混入canvas指纹)] )
 *   —— 含时间戳（有时效）+ 绑浏览器 DOM（不可纯移植），必须在真实浏览器页面里跑。
 *
 * ── 如何重新 dump 完整源码 ────────────────────────────────────────────────
 *   见 STATSIG_SIGNER_PLAN.md §4：route 注入暴露 window.__grokSigner / __grokSignerFactory
 *   后，对其 .toString() 即可拿到当前部署版本的完整混淆源码。
 * =========================================================================== */
