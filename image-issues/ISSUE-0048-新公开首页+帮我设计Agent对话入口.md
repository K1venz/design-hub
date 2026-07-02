---
id: ISSUE-0048
title: 实朴新公开首页（对外落地页）+「帮我设计」真 Agent 对话入口（方案 C 零框架 tool-use）
status: 已确认        # 用户已签设计稿、实现棒开闸（coordinator #874）；非 bug，借状态机表「已确认=确认要做」
severity: P1          # toC 上线关键能力：对外落地页（补 7.G）+ 对话式创作入口（交互代差补齐）
reporter: PM          # 用户拍板设计稿（2026-07-02），coordinator kickoff #874，PM 开条追踪
owner: 开发           # dev 第一棒（文本 LLM 探明 + 方案 C 后端）+ frontend-b（首页+/chat+登录墙）并行；PM 已交 PRD
created: 2026-07-02
updated: 2026-07-02
related:
  - 设计稿（实现权威）: docs/superpowers/specs/2026-07-02-public-home-agent-chat-design.md
  - 调研（方案 C 权威）: 调研-DeerFlow式对话创作入口-2026-07.md（da03710，结论=零框架 tool-use、不整接 DeerFlow）
  - PRD: §3.14 新公开首页 + 帮我设计（PM 本轮落）；§7.G 落地页在建标记；§7.B 内容安全公众前置提醒
  - code: 复用 image-code 现有 POST /listing/{generate,clone,edit} + SSE + CostGuard + UserRateLimiter + uploads（零新出图链路）
  - 群聊: image-gen#1 #874（kickoff）/#875-#879（三方 ACK + coordinator 裁定）
---

## 定性（用户已签，2026-07-02）
把当前「登录后即工作台」升级为：**公开落地页首页**（未登录可浏览、动作才登录墙）+ **真 Agent 对话入口「帮我设计」**（方案 C 零框架 tool-use，把现有三出图链路当工具，复用成本守卫/频控/owner 隔离、不绕卡体系、不造新出图链路）。借 DeerFlow 的「形」（流式+步骤可见）不借它的「体」（多服务 harness、不引 LangGraph/litellm）。

## 范围（PRD §3.14 全，实现权威=设计稿+调研方案 C）
- **新公开首页**：左竖导航 6 项（首页/帮我设计[内测标]/商品套图/爆款复刻/历史/管理[仅 manager]）+ 右上「内测免费」徽标（不放会员/价格入口）+ Hero（大聊天框+6 快捷卡）+ 工具区（双 banner 套图+复刻/宫格 单图·二次编辑·历史/≤2 张「即将上线」卡）+ 成果区（占位+懒加载）+ Footer（真《用户协议》《隐私政策》页 + ICP 备案号占位）。**未登录可浏览、点动作才登录墙、回跳继续**。
- **帮我设计 Agent（方案 C）**：`TextLLMPort`+OpenAI 兼容 chat 适配器 + `ChatOrchestrator`（application/chat/）+ `POST /chat` SSE；登录必须；出图前对话内**费用确认**；MVP 会话内存态不落库（避 DB 签字）；文本 LLM 首选 DeepSeek V4-Flash 直连（dev 探明、需新开 key/供应商=STOP 报用户）。

## 已定铁律（coordinator #878 裁定，实现前提）
1. **agent 只产 /listing 请求体字段、永不直接产 prompt 给图像模型**——LLM 输出=结构化参数，prompt 组装仍走 PromptComposer 卡链，**卡体系一字节不绕**。
2. **7.B 内容安全 = 公众全量硬前置**（对话把自由文本面扩到开放聊天）；MVP 仅登录内测/白名单。
3. **单会话出图单数上限 = 采纳**（dev 给保守默认如 ≤5 单、可配置，复用现有频控/成本守卫之上加会话级闸）。
4. **chat 的 clone 工具用现行契约**（参考风格/高度复刻），**不踩完全复刻 WIP**（`test_clone_blocks_match_card` 红=卡改码未跟，§3.13 🔄 改版独立推进）。
5. MVP 会话内存态不落库；**确需建表→STOP 报 coordinator 走用户签字**（DB 铁律）。

## 验收标准（PRD §3.14 ⑤，spec §六 7 条细化；QA 后续拉入）
1. 公开浏览 + 登录墙回跳（P0）。2. 三条真路径真出图（P0，套图/clone/edit，走现有 listing_job）。3. 出图前费用确认 + 对话触发出图受同一频控/红线（P0）。4. 成果区懒加载不阻塞首屏（P1）。5. Footer 协议页真实、注册页链接指向（P1，联动 7.E）。6. 现有工作台/套图/复刻/编辑/历史/管理零回归（P0）。7. 即将上线卡不可点标注清晰（P2）。8. fail-fast（P1，LLM 不可用报错、参数错走 400、不静默兜底）。

## 分工（spec §七 / coordinator #874）
- **PM**：PRD §3.14 + §7.G 标记 + 本 ISSUE + 验收细化 ✅（本轮交付）。
- **dev**：文本 LLM 探明（需新开 key STOP）→ 方案 C 后端四件（Port/适配器/Orchestrator//chat SSE+费用确认协议）+ openapi 再生；MVP 内存会话。
- **frontend-b**：新公开首页全版块 + `/chat` 会话页 + 路由/登录墙改造（`/`→新首页、套图工作台挪 `/set`、内部零改只换壳）+ Footer 协议页 + codegen。
- **QA**（后续拉入）：验收 ①-⑧ + 三条真路径真出图回归。
- **coordinator**：spec 权威、卡点裁决、审查闸、部署编排（上线前 qa 先行+备份可回滚）。

## 放量边界
MVP 内测灰度、**非公众全量**（7.B 内容安全前置未做 + §7.A 域名 ICP 备案仍卡、现走 IP，两条上线线独立）。

## 处理记录
- 2026-07-02 [PM] 用户签设计稿（2026-07-02）→ coordinator kickoff #874 点名 PM 第一棒。PM 落 PRD §3.14
  （页面结构 + 方案 C Agent + 验收 8 条 + 范围外 + 风险）+ §7.G 落地页「在建」标记 + 开本条。
  提三条对齐（agent 只产请求体字段/7.B 登录内测/单会话出图上限）→ coordinator #878 全采纳、dev #879 认同。
  owner=开发（dev 文本 LLM 探明 + 后端 / frontend-b 首页+/chat 并行，A 批前端已 #875 开工）。
  前端路由重构（`/`→新首页、套图挪 `/set`、内部零改）frontend-b 拍、coordinator #877 认可（纯前端非安全决策）。
- 2026-07-02 [前端] frontend-b A 批完成（commit efc5019，不依赖 dev chat 后端）：新公开首页 HomePage（Hero 大聊天框+6 快捷卡+工具区双 banner/宫格/≤2 即将上线卡+成果区占位懒加载+Footer 真协议链接/备案占位）+ 全局左侧竖导航 SideNav（6 项，替旧 2 项 rail，AppShell 统一外壳，AppTopBar 容忍未登录+内测免费徽标）+ 登录墙（ProtectedRoute state.from 回跳含 query，Login/Register 读 from 回跳）+ 路由重构（/→新首页公开、套图挪 /set、/chat A 批占位携首句、/terms+/privacy 公开协议页 LegalDoc，RegisterPage 勾选 #→协议页）。门禁 eslint/tsc/vitest 31 绿/build 全过；qa env 全流程实拍（首页未登录全版块/登录墙/注册回跳/套图新壳零回归/协议页/chat 占位，截图入 image-web/docs/screenshots/）。B 批（/chat 真流）按 dev 契约 0048（ad14a8a+431d696）待 mock 骨架落 qa 联调。
- 2026-07-02 [前端] frontend-b B 批核心完成（commit 0bccc88，按 dev 冻结契约 ad14a8a+431d696）：/chat 真流式对话页——lib/chat.ts（parseChatEvent 全事件 + job_event 信封解包复用 parseListingEvent + applyChatEvent reducer，10 单测）+ api/chat.ts（fetch+ReadableStream SSE 读取器，Bearer 头+POST body 非 EventSource）+ ChatPage（流式气泡/步骤条/工具透明/费用确认卡[确认·取消→POST confirm]/出图结果卡[复用工作台槽]/带图复用 /uploads/?q= 自动首条/session 内存态纯 useState/AbortController 清理/错误事件提示）。门禁 eslint/tsc/vitest 41 绿/build 全过；qa env 空态渲染验证无崩。真流式 send/confirm 的 live 行为待 dev mock 骨架落 qa 联调。
- 2026-07-02 [dev] 第一棒**文本 LLM 探明 → 命中 STOP（报用户）**：apinebula 现有 `GPT_IMAGE_API_KEY`（2 key）实测**均『仅图像』权限组**——`/v1/models` 只返 gpt-image-2 系；`/v1/chat/completions` 打 deepseek-chat/gpt-4o-mini/qwen-plus/glm-4-flash 全 **403 no access**。→ 文本需用户另开 key/access（路 A：apinebula 开文本权限/新建含文本 token，同站同发票口，推荐；路 B：单独接 DeepSeek 官方）。选型建议 deepseek-chat（中文强/tool calling 稳/极低价）。**已 STOP 报 coordinator 转用户（#882），A/B 待用户拍。**
- 2026-07-02 [dev] **/chat SSE 契约草案 → 三方冻结**：`docs/帮我设计-chat-agent-技术契约-0048.md`（commit ad14a8a + #884 五条硬化 431d696）。两端点 POST /chat/messages（流式一轮）+ POST /chat/confirm（显式费用确认，独立 token）；job 出图=包一层 job_event 转发 listing TaskEvent（前端零第二条流）；confirm_token 一次性+绑 session/user+TTL10min；会话级出图闸 chat_session_max_jobs=5 可配；估价取 registry unit_cost 与工作台同源。frontend-b UI 侧 ACK（#887）+ coordinator 正式冻结（#888/#890）。
- 2026-07-02 [dev] **方案 C 后端四件完成**：① `refactor(listing)` 抽 `ListingJobLauncher`（commit fdfc99e）——三出图路由内联的校验→频控→载图→建 Command→入队抽为 application 层单一事实源，路由退薄壳、orchestrator 同调（#884⑤ 不绕 interface 校验、不 HTTP 自调用）；顺带 SOLID 层次整顿（请求 DTO 迁 application/listing/requests、频控迁 application/rate_limit）。行为逐字对齐、既有 68 单测保绿（零回归）。② `feat(chat)`（commit 7abc5b4）：TextLLMPort + mock_text（规则驱动）/openai_compat_text（真实待 key）适配器 + InMemorySessionStore（内存会话+confirm_token）+ ChatOrchestrator（零框架 tool-use：澄清→结构化 tool args=/listing 请求体→费用闸→确认经 launcher 出图→转发 job_event→收尾）+ /chat 两路由 + openapi 再生含 /chat。③ `chore(config)` REAL_GPT_IMAGE 开关（ee71fc3，供本地 mock 联调）。铁律落点：LLM 只产请求体字段、prompt 仍走卡链（①）；MVP 内存会话不落库（⑤）；clone 走现行契约（④）。
- 2026-07-02 [dev] **端到端验证全 PASS + mock 骨架 LIVE**：无 key 全 mock（mock 文本+mock 图像+真 event bus/queue+sqlite）验证套图5张全链 + 一次性token重放拒 + 澄清轮 + 跨用户隔离 + cancel + clone；ruff/mypy 绿。起本机 mock 后端 `http://127.0.0.1:8000`（REAL_GPT_IMAGE=false 零成本零 prod 触碰）+ HTTP 实测全链通，交付 frontend-b live 联调（#892，同机无需隧道）。**真图渲染的「流式实拍」需 server qa 真 TOS（ops runbook）或 REAL_GPT_IMAGE=true+nginx**——mock 联调只验流式/步骤/费用闸/job_event 落位。
- 2026-07-02 [前端] frontend-b B 批 live 联调（本机 mock 127.0.0.1:8000）全链通过（commit dadbbc3）：snapshot 逐帧实证 ?q= 自动首发→澄清 / 带图上传→套图消息→步骤条→费用卡（5 张 ¥2.0000）→费用闸（输入禁用）→确认→job_event 逐张→出图结果 5/5→收尾「已完成」→输入重启用；job_event 复用 parseListingEvent 落槽正确、前端零第二条流。联调中抓并修 StrictMode 双挂载 abort seed 首发流的真 bug（改发新消息时才中止上一条在途流）。mock:// 图不渲染=预期，真图流式实拍待 dev 换真 provider（用户 key 路 A/B 待拍）→ qa env。门禁 eslint/tsc/vitest 41 绿。
- 2026-07-02 [前端] frontend-b 真图流式实拍完成（qa 真豆包+真gpt+真TOS，commit 390841a）：全链 ?q自动首条→真豆包澄清(业务上下文完整/零推理泄漏)→带图上传→套图消息→步骤条→费用卡(5张¥2.0000)+费用闸→确认→真gpt出图5/5(产品保真跨图一致)+自然收尾→输入重启用；后端 job e3a01e97 完成 n=5 cost=2.0000 真图落 qa TOS，一套控成本。观感反馈：出图轮无前置文字气泡(步骤条直跳费用卡)、可接受、暖场nudge可选不阻塞。小polish(低优backlog)：用户气泡自传图缩略图 qa 不渲染(/uploads预览url破图)、出图真图正常。截图 chat-real-costconfirm/chat-real-result 入 docs/screenshots。→ 待 QA 跑 0048 验收 8 条。
- 2026-07-02 [前端] frontend-b 当场修缩略图破图（commit 8958cf6）：用户气泡/输入 chip 拿 UploadResponse.url="/uploads/{id}" 作 <img> 破图，根因两层——① 缺 /api 代理前缀（无前缀被当前端路由返 SPA html=200 非 401）② 缺 ?access_token=（原生 img 不能带 Bearer）。修 uploadPreviewUrl 拼 /api+token；实证 /api/uploads/{id}?access_token=→200 image/png。工作台 ImageUploader 用本地 blob 故没踩坑。
