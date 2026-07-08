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
