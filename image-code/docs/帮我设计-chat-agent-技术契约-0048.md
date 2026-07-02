# 「帮我设计」真 Agent 对话入口 — 技术契约草案（ISSUE-0048 / 方案 C）

- 日期：2026-07-02
- 作者：dev
- 权威：`docs/superpowers/specs/2026-07-02-public-home-agent-chat-design.md`（用户已签）+ PRD §3.14 + ISSUE-0048
- 状态：**草案，待三方（dev/frontend-b/coordinator）对齐**；SSE 事件契约冻结前 frontend-b B 批以此为准
- ⚠️ 有一处**待用户拍板阻塞**（文本 LLM key/access，见 §0），不阻塞前端 B 批 UI 与本契约对齐

---

## 0. 文本 LLM 探明结论（STOP 已上报）

- apinebula 是 new-api 型 OpenAI 兼容中转站。现有 `GPT_IMAGE_API_KEY`（2 key round-robin）**两把都是「仅图像」权限组**：
  - `GET /v1/models` 仅返回 `gpt-image-2 / -pro / -vip`；
  - `POST /v1/chat/completions` 打 `deepseek-chat / gpt-4o-mini / qwen-plus / glm-4-flash` **全部 403 `This token has no access to model X`**。
- 403 文案=「无权访问模型」而非「模型不存在」→ 平台本身认得这些文本模型，缺的是**本 token 组的文本权限**。
- **结论**：需新开 key/文本 access = 用户的钱/账号/发票范围 → 已 STOP 报 coordinator 转用户。路 A（apinebula 开文本权限/新建含文本 token，同站同发票口，推荐）/ 路 B（单独接 DeepSeek 官方）。选型建议 `deepseek-chat`（V3，中文强、tool calling 稳、≈¥1/百万输入 token）。
- key 落定后仅需在 `.env` 加 `TEXT_LLM_*`（base 可复用 apinebula/v1），换真 provider 联调。**Port/Orchestrator//chat SSE 全 provider 无关，现在即可先行搭骨架 + 用 mock 联调前端。**

---

## 1. 架构（六边形内嵌、零新框架依赖）

```
interface/api/routes/chat.py   ── POST /chat/messages (SSE) / POST /chat/confirm (SSE)
        │
application/chat/orchestrator.py ── ChatOrchestrator（多轮澄清→选工具→组装请求体→确认→启 job→转发 job 事件）
        │                              └ 复用 ListingJobLauncher（见 §4 重构）→ 频控/owner/成本/卡链全继承
        ├── ports/text_llm.py        ── TextLLMPort（抽象：chat + tool-calling，流式）
        │       └ infrastructure/providers/openai_compat_text.py（DeepSeek 等；httpx 可注入）
        │       └ infrastructure/providers/mock_text.py（前端联调/CI 用，is_live=False）
        └── application/chat/session_store.py ── 内存会话（单进程 dict，MVP 不落库）
```

- **TextLLMPort**：唯一职责 = 给定 messages + tool schemas，返回（流式）assistant token 与结构化 tool_call。fail-fast：不可用→明确报错，不装死；4xx 不重试（I/O 域 429/5xx 可重试）。
- **ChatOrchestrator**：零框架 tool-use 循环——喂系统提示（澄清品类/图型/张数/比例/文案）+ 工具 schema → LLM 产 tool_call（=/listing 请求体字段）→ 费用确认闸 → 用户确认 → 经 Launcher 启 job → 转发 job SSE → 收尾。
- **内存会话**：`session_id → [messages] + 出图计数`，进程内 dict，刷新/重启即失（对齐 spec §四）。**确需落库 = STOP**。

---

## 2. `/chat` SSE 契约（frontend-b B 批事实源）

两个端点都：**Bearer 头鉴权**（`CurrentUserDep`，登录必须）+ 返回 `text/event-stream`（`StreamingResponse`）。
前端用 **fetch + ReadableStream 读流**（非原生 EventSource——因为要 POST body 且带 Bearer 头；不走 `?access_token=`）。

### 2.1 `POST /chat/messages` — 发一句话，流式收一轮

请求体：
```json
{ "session_id": "abc123 | null", "message": "给我的花生出一套5张", "upload_ids": ["u1","u2"] }
```
- `session_id` 首轮传 `null`，服务端建会话并在首个 `session` 事件回传；前端 useState 持有（内存态，刷新即失）。
- `upload_ids`（选填）：来自**现有** `POST /uploads`，带图路径（clone/edit）复用，不造新上传链路。

SSE 事件序（`event: <type>\ndata: <json>\n\n`）：

| event | data | 含义 |
|---|---|---|
| `session` | `{session_id}` | 会话建立/确认（首个事件） |
| `assistant_delta` | `{text}` | assistant token 流（气泡增量） |
| `step` | `{phase, detail}` | DeerFlow 步骤条。`phase ∈ understood\|planning\|generating\|done`，如 `{"phase":"understood","detail":"花生·白底套图·5 张"}` |
| `tool_call` | `{tool, args}` | 工具调用透明化。`tool ∈ generate\|clone\|edit`；`args` = 组装好的 /listing 请求体（见 §3） |
| `cost_confirm` | `{confirm_token, tool, args, count, unit_cost, estimate_cny}` | **费用确认闸**：服务端在此**暂停不出图**，本轮流在此收尾 |
| `assistant_end` | `{status}` | 一轮终止符。`status ∈ complete\|awaiting_confirm\|error` |
| `error` | `{code, message}` | fail-fast（见 §5） |

- 若这轮只是澄清对话（未触发出图）：`session`→`assistant_delta*`→`assistant_end{complete}`。
- 若这轮触发出图：…→`tool_call`→`cost_confirm`→`assistant_end{awaiting_confirm}`。**此时不产生 job、不扣费。**

### 2.2 `POST /chat/confirm` — 显式确认/取消出图（费用闸的用户动作）

请求体：
```json
{ "session_id": "abc123", "confirm_token": "ct_xxx", "action": "confirm | cancel" }
```
- `action:"cancel"` → 单个 `assistant_delta`（「已取消」）+ `assistant_end{complete}`，不出图。
- `action:"confirm"` → 服务端经 Launcher 启 job，流式回传：

| event | data | 含义 |
|---|---|---|
| `job_started` | `{job_id, tool, count}` | job 已入队 |
| `job_event` | `{job_id, type, data}` | **包一层**转发现有 listing SSE 的 `TaskEvent`（见 §2.3） |
| `assistant_delta` | `{text}` | 收尾话术（「5 张已出好」） |
| `assistant_end` | `{status}` | `complete\|error` |

### 2.3 job 出图事件 = 包一层转发（回答 frontend-b Q）

**不让前端再开第二条 EventSource。** Orchestrator 内部 `EventStream.subscribe(job_id)`（复用现有进程内 EventBus），把每个 `TaskEvent` 原样包进 `job_event.data`：
```json
{ "job_id":"...", "type":"image_generated", "data":{"url":"...","seed":0,"image_type":"白底"} }
```
`type` 取值即现有 `TaskEventType`：`task_started / model_called / image_generated / image_failed / task_completed / task_failed`。**前端复用工作台已有的这套事件渲染逻辑**（结果卡/进度/部分失败），只是外层多了 `job_event` 信封。

---

## 3. 工具 = /listing 请求体字段（铁律落点）

LLM 的 tool schema 输出**逐字段对齐现有请求体**，`prompt` 字段=用户级意图文本（同工作台用户手输的那段），**绝不是喂给图像模型的最终 prompt**——最终图像 prompt 仍由 `build_listing_prompts / compose_clone_prompt / compose_edit_prompt` 卡链在 service 内组装。**Agent 一字节不绕卡体系**（PRD 铁律①）。

| tool | args（= 请求体） |
|---|---|
| `generate` | `upload_ids, prompt, ratio, n \| plan, overlay_texts?, modifiers?, category` |
| `clone` | `product_upload_ids, reference_upload_ids, clone_mode, ratio, prompt?, modifiers?, category`（clone_mode 用**现行契约** 参考风格/高度复刻，不踩完全复刻 WIP） |
| `edit` | `source_image_key, prompt, edit_mode, modifiers?, ratio?` |

校验口径复用路由现有 fail-fast（数量/枚举/互斥/overlay/图型卡/owner），见 §4。

---

## 4. 复用铁律：job 启动逻辑重构（old adapts to new）

现状：`generate/clone/edit` 三个路由各自内联「校验→`limiter.acquire`→载图/owner 校验→建 Command→`queue.enqueue`」。

重构：抽到 `application/listing/job_launcher.py` 的 `ListingJobLauncher.launch_generate/clone/edit(user, req) -> job_id`，**路由与 orchestrator 都调它**。这样 chat 出图自动继承：
- 频控 `UserRateLimiter`（5 单/分 + ≤2 in-flight）
- owner 隔离（`owns(uid, user_id)` → 404 防枚举）
- 成本守卫（`CostGuard` reserve/reconcile/rollback 在 service 内自洽）
- 卡链（PromptComposer 在 service 内）

路由退化为薄壳（旧码适配新架构，无兼容层/shim）。

---

## 5. 费用确认协议 + 会话级出图闸

- **估价口径与工作台一致**：`estimate_cny = unit_cost × count`，`count` = `n`（单图）/ `Σplan`（套图）/ `1`（clone/edit）。`unit_cost` 取自图像 provider（与 `listing_service` 同一 Decimal 源）。→ 验收③口径一致。
- **确认是显式独立动作**：`cost_confirm` 只给 `confirm_token`+估价，服务端暂停；用户在对话里点确认 → `POST /chat/confirm`。**防「聊着聊着被扣钱」。**
- **会话级出图闸**（PRD 铁律③）：设置 `chat_session_max_jobs: int = 5`（保守默认，可配）。在 confirm 启 job 前检查会话已启 job 数，超限 → `error{code:"session_job_limit"}`。叠加在既有 per-user 频控之上。
- **fail-fast 错误码**（`error.code`）：`llm_unavailable` / `budget_exceeded`（映射 402/域）/ `rate_limited`（429）/ `session_job_limit` / `bad_request`（4xx，不重试）。

---

## 6. Frontend-b 三问答复

1. **SSE 事件序 + 费用确认回传**：见 §2。费用确认 = **独立 `POST /chat/confirm` + confirm_token**（coordinator 定向：必须显式用户动作）。job 出图 = **包一层 `job_event` 转发**，前端不开第二条流、复用工作台事件渲染。
2. **MVP 会话内存态**：✅ 对齐。前端会话态纯 useState，刷新即失；`session_id` 首轮由服务端 `session` 事件下发。
3. **带图路径**：✅ 走现有 `POST /uploads` 拿 `upload_id` → 传 `messages.upload_ids`，不造新上传链路。

---

## 7. MVP 边界 / 待办

- 会话历史不落库（二期）；确需建表 = STOP。
- 「帮我设计」挂内测标、仅登录可用；公众全量前内容安全（PRD §7.B）硬前置（本期不做）。
- openapi 再生随 chat 路由落定一并跑。
