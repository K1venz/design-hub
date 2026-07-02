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
