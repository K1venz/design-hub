# 登录健壮性优化 — 设计稿

- 日期：2026-07-08
- 来源：用户「我们先来优化一下登录的健壮性」
- 状态：coordinator 定稿派单（方案 A 滑动续期，零建表零签字）

## 一、现状缺口（读码实锤）

1. **24h 必踢**：JWT HS256 固定 `jwt_ttl_hours=24`（settings.py:54），无 refresh/续期——活跃用户每天中途被「登录已过期」踢回登录页；「记住我」只记住到令牌过期，语义半空。
2. **多标签页不同步**：登出仅清本页 store（rememberAwareStorage 双清），无 storage 事件广播——другой标签页继续旧会话直到撞 401。
3. **限流/网络错非人话**：nginx /login 15r/m→429（非 JSON body）、断网 fetch 异常——前端 login.error.message 显示原始错误。

## 二、方案 A：滑动续期（sliding session）

**核心**：活跃即永续、不活跃 24h 过期（安全兜底不变）。

- **后端**（dev）：鉴权依赖处（CurrentUserDep 解析 JWT 后）判断令牌年龄——**已过半衰期（签发超 12h）**则签一张新 24h 令牌放响应头 `X-Renewed-Token`。无新端点、无表、无迁移；幂等（多请求并发各自带头无害）；exp 未过才续（过期仍 401 走原路）。SSE 长连接不续（无妨——下一个普通请求会续）。
- **前端**（frontend-b）：api client 响应中间件读 `X-Renewed-Token` → `useAuthStore.setToken`（经 rememberAwareStorage 落原存储位：localStorage/sessionStorage 跟随当前记住我模式，不升级不降级）。SSE fetch 流不经 openapi-fetch 的也要盖到（chat/job 事件流若独立 fetch，同样读头或依赖普通请求续即可——普通请求频度足够，SSE 不强求）。
- **安全边界**：续期只延长活跃会话；被盗令牌离线 24h 后照样死；jwt_secret 轮换仍全量失效。**不做服务端撤销**（无表、YAGNI，随二期 B 双令牌再议——记录 backlog）。

## 三、配套两件（同波）

1. **多标签页登出同步**（frontend-b）：`window.addEventListener('storage')` 监听 auth 存储键被清 → 本页 clear + 跳登录（仅登出方向广播；登录方向不强求）。sessionStorage 无跨页事件——仅 localStorage 模式生效（记住我=默认勾，覆盖主流）。
2. **登录/注册错误人话化**（frontend-b）：429（含 nginx 非 JSON body 解析失败情形）→「尝试太频繁，请稍等 1 分钟再试」；网络异常（fetch reject/超时）→「网络异常，请检查连接后重试」；401 维持「邮箱或密码错误」；409/400 维持现文案。

## 四、范围外（YAGNI，记 backlog）

方案 B 双令牌（30 天离线+服务端撤销+建表签字）；账号锁定/验证码（nginx 限流已挡暴力破解）；邮箱验证；登录设备管理。

## 五、验收要点

1. 半衰期前请求：无 `X-Renewed-Token` 头、令牌不变；半衰期后请求：响应带新令牌、前端无感换、存储位不变（记住我勾/不勾各验）。
2. 过期令牌仍 401 + 清会话跳登录（原语义零回归）。
3. 双标签页（localStorage 模式）：A 页登出 → B 页秒内清会话跳登录。
4. 登录页：连续快速提交触发 429 → 显示人话；断网提交 → 显示网络人话。
5. 全站零回归（登录/注册/受保护页/chat/工作台）。

## 六、分工

- **dev**：后端滑动续期（jwt_service 加 issue-age 判断 + CurrentUserDep 响应头注入；`jwt_renew_after_hours` 设默认 12 进 settings；pytest：半衰期前后/过期/头形态）。
- **frontend-b**：client 中间件读头换令牌 + storage 登出广播 + 登录错误人话化 + vitest。
- **QA**：验收 5 条（本机 mock 可全验，令牌年龄用短 TTL 配置加速）。
- **部署**：零迁移轮。
