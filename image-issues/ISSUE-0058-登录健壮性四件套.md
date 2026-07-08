---
id: ISSUE-0058
title: 登录健壮性四件套——滑动续期 + 密码传输公钥加密 + 多标签登出同步 + 错误人话化
status: 修复中        # spec 定稿派单、dev(后端2)+frontend-b(前端3)并行开工中；零建表零签字、与 key 事故无依赖插空档
severity: P2          # 用户直接提需求；登录体验/纵深安全硬伤修复（24h必踢/明文密码/多标签不同步/错误非人话）；非资损非阻断
reporter: PM          # 用户 2026-07-08 提需求（coordinator #1015 转达），spec 定稿 e75ddb1，PM 挂账
owner: 开发+frontend-b # 并行同波原子：dev(滑动续期+密码解密)、frontend-b(读头换令牌+WebCrypto加密+storage登出+错误人话)
created: 2026-07-08
updated: 2026-07-08
related:
  - PRD: §3.17 登录健壮性四件套
  - spec: docs/superpowers/specs/2026-07-08-login-robustness-design.md（coordinator 定稿 e75ddb1）
  - issue: §7.A ICP 备案（密码加密根治=备案后正式域名+LE 证书，本层是纵深防御永久保留）
  - code: image-code jwt_service/CurrentUserDep/settings(jwt_ttl_hours·新增 jwt_renew_after_hours)、auth routes(login/register/新 /auth/pubkey)；image-web api client 中间件/auth-store/rememberAwareStorage/LoginPage/RegisterPage
  - 铁律: 零建表零签字（RSA 私钥走 .env/文件不入库）→ 无 DB 门；fail-fast（公钥拉取失败报错不回退明文=假加密纪律）
  - 群聊: image-gen#1 #1015（coordinator 派单）
---

## 定性（用户 2026-07-08 提需求，coordinator #1015 转达）
用户「先优化登录的健壮性」+ 追加拍板「密码传输公钥加密」→ spec 定稿派单。**零建表零签字**（RSA 私钥走 .env/文件不入库、明确「方案 A 零建表零签字」）、与 P0 key 事故无依赖、纯登录链路、插空档执行。

## 现状缺口（读码实锤）
1. **24h 必踢**：JWT HS256 固定 `jwt_ttl_hours=24`、无 refresh/续期 → 活跃用户每天中途被踢、「记住我」语义半空。
2. **多标签页不同步**：登出仅清本页 store、无 storage 广播 → 别页续旧会话至撞 401。
3. **限流/网络错非人话**：nginx 429 非 JSON body、断网 fetch 异常 → 前端显原始错。
4. **密码明文仅靠 TLS**：prod 自签证书、用户点警告访问=TLS 实际削弱 → 纵深防御缺一层。

## 四件套
- **①滑动续期（方案 A，dev）**：活跃永续、不活跃 24h 过期（安全兜底不变）。`CurrentUserDep` 解析 JWT 后判令牌年龄——签发超 `jwt_renew_after_hours`（settings 默认 12）则签新 24h 令牌放响应头 `X-Renewed-Token`；**零端点零表零迁移**、幂等、exp 过期仍 401 原路（SSE 长连不续、下个普通请求会续）。前端 client 响应中间件读头→`setToken`（rememberAwareStorage 落原存储位、不升降级）。
- **②密码传输公钥加密（dev+frontend-b）**：服务器生成 RSA-2048（私钥 .env/chmod600、**不入库不入 git**、qa/prod 各生成）；`GET /auth/pubkey` 公开返 SPKI PEM；login/register 密码字段收 `base64(RSA-OAEP-SHA256)`→解密→**bcrypt 照旧**；解密失败 400 人话。前端 WebCrypto，**公钥拉取失败=报错不回退明文（假加密纪律）**。⚠️ **bcrypt/最短 8 位校验语义不动**（min_length 挪解密后明文）。
- **③多标签登出同步（frontend-b）**：`storage` 事件监听 auth 键被清→本页 clear+跳登录（仅登出方向；仅 localStorage 模式=记住我默认勾覆盖主流）。
- **④错误人话化（frontend-b）**：429→「尝试太频繁，请稍等 1 分钟再试」；网络异常→「网络异常，请检查连接后重试」；401 维持「邮箱或密码错误」；409/400 维持现文案。

## 安全边界（诚实入档）
密码加密层挡**被动嗅探/日志泄漏/自签场景偷看**；**不挡全能主动 MITM**（能改 JS）→ **根治=备案后正式域名+LE 证书**（联动 §7.A、本层纵深防御永久保留）。不做前端哈希（pass-the-hash 假安全）、不做 SRP（YAGNI）、不做服务端撤销（无表 YAGNI，随二期方案 B 双令牌再议·backlog）。

## 部署纪律
前后端**必须同波原子上**（密码字段格式变）；旧缓存 bundle 发明文→400 清晰报错刷新即愈（内测规模可接受）。零迁移轮（用户预授权绿即上）。

## 验收标准（QA，spec §五 6 条）
0. 抓包 login/register 请求体**无明文密码**（密文 base64）+ 错密文 400 + 公钥接口挂→前端报错不发明文 + bcrypt 存储不变、老账号照常登录。
1. 半衰期前：无 `X-Renewed-Token`、令牌不变；半衰期后：带新令牌无感换、存储位不变（记住我勾/不勾各验）。
2. 过期令牌仍 401 + 清会话跳登录（原语义零回归）。
3. 双标签页（localStorage）：A 登出→B 秒内清跳登录。
4. 429/断网显人话。
5. 全站零回归（登录/注册/受保护页/chat/工作台）。

## 范围外（YAGNI，backlog）
方案 B 双令牌（30 天离线+服务端撤销+建表签字）/ 账号锁定·验证码（nginx 限流已挡暴力破解）/ 邮箱验证 / 登录设备管理。

## 处理记录
- 2026-07-08 [PM] 用户提需求（coordinator #1015 转达，spec 定稿 e75ddb1）→ PM 挂账：落 PRD §3.17 + 开本条。
  **零建表零签字确认**（RSA 私钥走 .env/文件不入库→无 DB 铁律门）、与 P0 key 事故无依赖、插空档执行。
  分工（并行同波原子）：dev（后端滑动续期 + 密码解密 + /auth/pubkey + pytest）；frontend-b（client 读头换令牌 + WebCrypto 加密 + storage 登出广播 + 错误人话 + vitest）；
  **前后端必须同波原子上**（密码字段格式变）。验收 6 条（含抓包无明文密码 + 假加密纪律 + 零回归）。
  **诚实边界入档**：本层挡被动嗅探/自签场景、不挡全能主动 MITM，根治=§7.A 备案后正式域名+LE 证书。QA 本机 mock 全验零成本、短 TTL 加速续期验证 → 零迁移轮部署（coordinator 编排）。**仍内测灰度**（7.B/7.A 前置不变）。
  status=修复中、owner=开发+frontend-b（并行开工）。**排队**：插当前空档（与 key 事故无依赖），真实用户 bug 随时打断。
- 2026-07-08 [frontend-b] **前端三件完成**（commit `98cb316`，纯 image-web 6 文件）+ **发 dev wire 契约对齐**（#1017）：
  ① 滑动续期换头——`api/client.ts` 响应中间件读 `X-Renewed-Token`（裸 JWT）→ `setToken`，经 rememberAwareStorage 落原存储位
     （记住我模式不升级不降级）。② 密码公钥加密——新 `api/crypto.ts`：`GET /auth/pubkey`（容错 text/plain PEM 或 JSON{public_key}）
     → WebCrypto importKey(SPKI)+encrypt(RSA-OAEP-SHA256)→base64 密文；login/register 密码字段改传密文（email/name 明文）；
     **假加密纪律**=公钥拉取失败抛「安全通道初始化失败」绝不回退明文；公钥进程内缓存、失败清缓存可重试；register 仍先校验明文≥8 再加密。
     ③ 多标签登出 + 错误人话——`MultiTabLogoutWatcher`(App.tsx) 监听 storage 事件（另一标签清 auth 键→本页 clear+跳登录、仅 localStorage 模式、
     只广播登出方向）、auth-store 导出 `AUTH_STORAGE_KEY`；login/register 错误人话化（429→「尝试太频繁，请稍等 1 分钟」、断网→「网络异常，请检查连接后重试」、401/409/400 维持后端文案）。
  **门禁四件套全绿**（lint/tsc/vitest **58** 含 +4 crypto 纯函数测试/build）。**本地 mock + Playwright 实证验收#0 安全关键路径**：
     公钥端点不可用(400)→登录报「安全通道初始化失败」+ **网络仅 GET /auth/pubkey、零 POST /auth/login=零明文密码外发**（假加密纪律守住）。
  **wire 契约已发 dev**（#1017）：pubkey 两式容错·密码 base64(RSA-OAEP-SHA256 密文)·X-Renewed-Token 裸 JWT·请 dev 确认 nginx 透传该头不 strip。
  **待联验**（需 dev 后端 /auth/pubkey+解密+X-Renewed-Token 共存，原子上线本质）：happy-path 加密↔解密登录 / 续期换头无感 / 存储同步双标签 / 429·网络人话——
  dev 后端进 mock 后我补一次联调，或 QA 一轮联验（本机 mock 全验+短 TTL 加速续期）。owner 前端份完成、待 dev 后端就位联验 → coordinator 编排 QA → 同波原子部署。
- 2026-07-08 [dev] **后端两件完成**（commit `a6feefc`，零建表零迁移；按 coordinator #1019 拍板 wire 契约实现）：
  **① 滑动续期**——`TokenService.renew_if_stale`（jwt_service）：令牌签发超 `jwt_renew_after_hours`（settings 默认 12）则签新 24h 令牌；
     `get_current_user` verify 成功后调、非 None 放响应头 `X-Renewed-Token`（**裸 JWT**，契约③）；**exp 已过仍 verify 抛 401 原路**（不续过期）；
     幂等、零端点零表。SSE 依赖 `get_current_user_sse` 不续（普通请求频度足够，spec §二）。
  **② 密码传输公钥加密**——`PasswordCipher` 端口 + `RsaPasswordCipher`（**RSA-OAEP + MGF1(SHA-256) + SHA-256**、无 label、UTF-8，与前端 WebCrypto 对齐，契约②）；
     私钥留 `.env`（`AUTH_RSA_PRIVATE_KEY_PEM` 不入库不入 git）、未配则启动生成临时（local/CI 自足）；`GET /auth/pubkey` 公开返 **JSON `{"public_key": "<SPKI PEM>"}`**（契约①）；
     login/register 路由**边界解密**密文→明文（解密失败→**400 人话「密码解密失败，请刷新页面后重试」**，旧缓存 bundle 发明文即命中）→ AccountService 收明文；
     **min≥8 校验在明文**（AccountService 内，schema 去 `min_length=8`）；**存储侧 bcrypt / AccountService 零改**（SRP：传输解密在 interface 边界，账号逻辑不知密码曾加密）。
  **nginx 透传**：coordinator #1019 已查死——现配置无 `proxy_hide_header`、默认透传上游自定义响应头，`X-Renewed-Token` 原样到前端、**无需改 nginx**。
  **测试** `test_auth` 13 绿：renew 半衰期前(无头)/后(有头+新令牌可用)/过期(401) + RSA 往返/垃圾→ValueError/from_pem + 集成（pubkey shape / 密文注册登录往返 /
     解密失败 400 / 明文<8→400（证校验挪明文）/ /me 过半衰期回 `X-Renewed-Token` / fresh 无头 / 过期 401）。openapi 再生（+/auth/pubkey +PubKeyResponse、password minLength 8→1）。
     ruff+mypy(src) 绿、pytest **119 绿 + 1 已知 WIP 红**。
  **交接**：后端就位 → @frontend-b 联调 happy-path（真 WebCrypto 加密 ↔ 后端解密 / 续期换头无感）→ coordinator 编排 QA 6 条 → **同波原子部署**（密码字段格式变、前后端必须同波）。
- 2026-07-08 [frontend-b] **前后端 happy-path 联调全绿**（commit `9330f23` pubkey 解析加固 + `3b080f0` codegen 同步；起 dev a6feefc 后端 mock 实测）：
  ① **pubkey 加固**（`9330f23`）：按 coordinator #1019 拍板 pubkey=JSON 式，crypto.ts 改「文本 trim 后以 { 开头即 JSON.parse 取 public_key、否则裸 PEM」不依赖 Content-Type（防原子上线头抖动）；malformed 仍 fail-fast。
  ② **codegen 同步**（`3b080f0`）：拉入 dev openapi 的 /auth/pubkey+PubKeyResponse（前端 crypto 走 raw fetch 不依赖该端点类型，纯 schema 对齐）。
  **Playwright + dev 后端 mock（JWT_RENEW_AFTER_HOURS=0 强制续期）联调实证**：
  · **加密↔解密 roundtrip**：`/auth/pubkey` 返 JSON `{"public_key":"-----BEGIN PUBLIC KEY-----…"}`→WebCrypto 加密→后端 RsaPasswordCipher 解密→bcrypt。
    **老账号照常登录**（remember@example.com=旧明文 bcrypt 哈希，密文登录 200 ✓=验收#0 老账号）+ **新用户加密注册**（robust58@example.com 注册→登录态 ✓）。
  · **抓包无明文**（验收#0）：login POST body `password`=base64 RSA-2048 密文（344 字符 `KnaK2BeO…==`）、**非明文**；email 明文 ✓。
  · **滑动续期换头**（验收#1）：`/me` 响应带 `x-renewed-token`（裸 JWT iat=新）→ client 中间件 setToken → localStorage token 换成续期后的（iat/尾匹配）、**落 localStorage 原位不升降级**（记住我模式，inSession=false）✓。
  · **双标签登出同步**（验收#3，localStorage 模式）：Tab A(/)退出登录写 null-token → **Tab B(/history)storage 事件秒内清会话+跳 /login** ✓。
  · **fail-fast 无明文**（验收#0 泄漏面，早前无 pubkey 时验）：公钥端点不可用→登录报「安全通道初始化失败」+ 零 POST /auth/login ✓。
  **本地未覆盖**：429（nginx 限流 mock 产不出）+ 断网人话——代码路径直白（429→固定文案、fetch reject→固定文案）、交 QA server-side 一轮（真 nginx 429）。
  **联调结论**：happy-path + 安全关键路径全绿、跨语言 RSA-OAEP-SHA256 interop 干净、契约逐项对齐。前后端就绪 → @coordinator 编排 QA 6 条 → 同波原子部署。owner 前端份联调完成、球交 coordinator。
