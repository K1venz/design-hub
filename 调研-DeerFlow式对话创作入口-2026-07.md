# 调研：能否接入 DeerFlow 式 agent harness，把实朴做成「对话式创作入口」

- 调研人：技术调研（Research）
- 调研时间：2026-06-30 ～ 07-01
- 对标物：美图设计室 Agent 入口（页面中央大聊天框「和我聊聊，你想要创作什么？」+ 分类快捷卡（电商设计/海报设计/视频创作/社媒营销/品牌设计/办公设计）+「AI 团队」按钮）
- 范围：只做调研与方案建议，不写代码、不改现有文件

---

## 0. 结论先行

**能不能做「对话式创作入口」？——能，而且实朴的地基比预想的好：三个出图端点（generate/clone/edit）天然就是三个「工具」，SSE 逐张回显、成本守卫、频控、owner 隔离全部现成，对话层只是在它们上面加一层「参数澄清器」。**

**要不要整接 DeerFlow？——不要。** DeerFlow 2.0（2026 年当前主线）已从「Deep Research 框架」重写为多服务「SuperAgent harness」（Gateway + agent runtime + 沙箱 + Next.js 前端 + 可选 K8s），与实朴「单进程、无 Redis、React SPA、复用优先」的约束全面冲突；v1（main-1.x 分支）虽轻些，但五角色（coordinator/planner/researcher/coder/reporter）与提示词都为「研究→报告」管线硬编码，改成「对话→出图编排」等于只留 LangGraph 骨架、其余全换——不如不搬。

**推荐路线：方案 C（零框架 tool-use 循环）**——在现有 FastAPI 内新增 `/chat` 路由族：自写一个 ~几百行的对话编排器（TextLLMPort + 单 agent + 3 个工具 = 现有三条出图链路），文本 LLM 首选 **DeepSeek 官方 API（V4-Flash，OpenAI/Anthropic 双兼容协议，工具调用原生支持，一次澄清会话成本 ≈¥0.05，约为一套图成本的 3%）**，前端在 React SPA 里自写 `/chat` 聊天页（复用 Style 4 玻璃质感 + 现有 EventSource 模式，出图卡片直接内嵌会话里逐张点亮）。**量级：MVP 约 8–12 人日**（后端 4–6 + 前端 3–4 + 联调 QA 1–2）。方案 B（Pydantic AI / LangGraph 轻编排嵌入现有 FastAPI）作为复杂度增长后的升级路径保留；方案 A（整接 DeerFlow）明确不推荐。

一句话：**借 DeerFlow 的「形」（对话入口 + agent 编排出图的产品形态），不借它的「体」（多服务 harness 工程）。**

---

## 1. DeerFlow 本体剖析

### 1.1 两代 DeerFlow：先分清版本，再谈改造

这是本次调研最重要的事实修正：**「DeerFlow」在 2026 年已经是两个几乎不相干的工程**。

| | DeerFlow v1（2025-05 开源） | DeerFlow 2.0（2026-02 底上线，2.0.0 release 2026-06-25） |
|---|---|---|
| 定位 | Deep Research 框架（深度研究→出报告/PPT/播客） | 「long-horizon SuperAgent harness」：研究、写代码、创作交付物，任务跑分钟到小时级 |
| 架构 | LangGraph StateGraph 固定五角色：Coordinator（接待/分流）→ Planner（拆解出 Plan/Step，含人审计划环节）→ Researcher（搜索/爬取/RAG）→ Coder（Python 执行）→ Reporter（汇总成稿） | Lead agent 动态孵化 sub-agent（各带独立上下文/工具/终止条件），配 sandbox（沙箱执行）、memory、skills（Markdown 技能包 `.skill`）、MCP（含 OAuth）、IM 渠道接入 |
| 后端 | Python + FastAPI（`server.py`，:8000） | Python + FastAPI（Gateway API）+ agent runtime，仍基于 LangGraph/LangChain |
| 前端 | **Next.js** web 应用 | **Next.js**（TypeScript 占仓库 ~15%） |
| LLM 接入 | `conf.yaml` + **litellm**（OpenAI/Qwen/DeepSeek/Azure/Ollama） | `config.yaml`，任意 OpenAI 兼容 API（官方推荐 Doubao-Seed-2.0-Code / DeepSeek v3.2 / Kimi 2.5），不再依赖 litellm |
| 流式 | SSE（`/api/chat/stream`） | SSE（values / messages-tuple / end 等模式） |
| 状态 | LangGraph MemorySaver（内存） | memory + sandbox 持久化，多服务 |
| 部署 | 单后端 + 单前端，有 Docker | **Docker 为中心的多服务**：Gateway、Frontend、Backend（agent runtime）、可选 Provisioner（K8s 模式）、nginx、IM channel workers；生产建议单 Gateway worker（流桥无 sticky session） |
| 许可证 | MIT | MIT |
| 活跃度 | 维护在 `main-1.x` 分支（legacy，仍接受贡献） | 主线；~75.8k stars / 10.2k forks / 2400+ commits；2026-02-28 登顶 GitHub Trending |

（来源见文末 [S1]–[S8]）

### 1.2 关键判断：改造成「对话式出图编排」要动多少

**v2 路线（主线）**：它是一个「产品级平台」而非「可嵌入的库」。要接入实朴意味着：多起一组服务（Gateway/runtime/沙箱），第二套前端（Next.js），第二套配置与运维面，跨服务转发 JWT、跨服务保住 CostGuard/频控闸门。它解决的问题（长时程任务、沙箱代码执行、动态 sub-agent、IM 接入）没有一个是「澄清参数→调三个出图端点」需要的。**对实朴等于引入一个比主业务还重的伴生系统，直接违背「无谓依赖不加、无 Redis、单进程」铁律。**

**v1 路线（main-1.x）**：贴近任务描述里的想象，但拆开看：
- 五个角色的节点逻辑和提示词全部围绕「研究计划→搜集→写报告」设计。对话出图场景里 Researcher/Coder/Reporter 整个作废，Planner 的 Plan/Step 数据模型也不适配「一次出图请求」的粒度；真正可复用的只有 Coordinator 的「接待→澄清→handoff」模式与 LangGraph 骨架。
- 它自带 litellm——而实朴 PRD §B4 有明确先例：**拒绝 LiteLLM，自建 AbstractModelProvider、对协议编程**（image-code 现有 `OpenAICompatImageProvider` 就是这么落的）。整接 v1 等于把已被否掉的选型又背回来。
- 前端是 Next.js。实朴是 **React 19 + Vite SPA（BrowserRouter 组件式路由）**，DeerFlow 的聊天 UI 组件深度绑定 Next.js 应用结构，不能直接搬，只能「看着重写」。
- v1 已是 legacy 分支，长期跟随上游获益趋零，fork 维护成本全自担。

**结论：DeerFlow 两代都不适合整接。它的价值是「参考答案」：对话入口的产品形态、SSE 流式 agent 事件的交互范式、「coordinator 澄清后编排」的角色划分思想，这些都可以在自己 ~几百行的实现里薅走。**

---

## 2. 备选 harness 对比

| 候选 | 语言/栈契合度 | 拿来做什么 | 改造/接入量 | 维护风险 | 判断 |
|---|---|---|---|---|---|
| **DeerFlow v2** | 后端 Python✓ 但多服务；前端 Next.js✗ | 整套平台 | 极大（第二系统） | 大版本重写先例（v1→v2 完全不共享代码），跟随成本高 | ❌ 排除 |
| **DeerFlow v1 (main-1.x)** | FastAPI✓、litellm✗、Next.js✗ | 拆 LangGraph 编排层 | 大（五角色全换、litellm 违反先例、前端重写） | legacy 分支 | ❌ 排除 |
| **LangGraph 裸用** | Python、MIT、1.0 GA（2025-10，承诺 1.x API 稳定）；InMemorySaver/SqliteSaver 不需要 Redis | 只取 StateGraph 做编排 | 中：学习曲线 + langchain-core 依赖族；对「单 agent+3 工具」的线性流程是杀鸡牛刀 | 低-中（1.0 已稳定；但引入 langchain 生态依赖树） | ⚠️ 备选（方案 B 之一） |
| **Pydantic AI** | **契合度最高的框架**：Pydantic 团队出品（pydantic 已是 image-code 核心依赖）、类型安全工具定义、模型无关（OpenAI 兼容/Anthropic/DeepSeek 原生 provider，不经 litellm）、FastAPI 亲和 | 单 agent + typed tools + 流式 | 小-中：依赖轻、心智模型贴 FastAPI | 中（框架仍在快速演进，接入前需核对当前版本 API 稳定性） | ⚠️ 方案 B 首选形态 |
| **OpenAI Agents SDK (python)** | Python✓；但 provider-native，接非 OpenAI 模型官方路径是 litellm 扩展 → 撞 PRD 先例 | handoffs/guardrails | 中 | 中（绑 OpenAI 生态） | ❌ 不选 |
| **Anthropic/OpenAI 原生 tool-use 循环（零框架）** | **完美**：httpx、pydantic 都已在依赖里；与现有 `OpenAICompatImageProvider`「对协议编程」完全同构；DeepSeek 官方同时提供 OpenAI 兼容与 Anthropic 兼容两种端点，一套循环可换模型 | 手写 agent loop（~200–400 行） | 小：无新框架依赖 | 最低（无框架 churn；代码量小到可全量掌控，fail-fast 好落） | ✅ **方案 C，推荐** |
| **CopilotKit（+AG-UI 协议）** | React UI✓（chat 组件、generative UI）；后端有 Python SDK 桥 FastAPI/LangGraph；AG-UI 已被 LangChain/PydanticAI/微软等采纳 | 前端对话 UI + 前后端 agent 协议 | 中：引入 Copilot Runtime/AG-UI 协议层与其事件模型，UI 风格需驯化成 Style 4 | 中（协议与组件层双依赖） | ⚠️ 仅当不想自写聊天 UI 时考虑 |
| **Vercel AI SDK（v6，Apache-2.0）** | 前端 TS✓：`useChat` 不要求 Next.js，React SPA 可用；后端任意语言可实现其 Data Stream Protocol（SSE），官方有 FastAPI 模板 | 只拿前端 `useChat` + 流协议 | 中：需在 FastAPI 侧实现其 v6 wire format（v5→v6 刚经历 4 组破坏性变更） | 中（协议 churn 明显） | ⚠️ 不建议为协议买单；自家 SSE 已够用 |
| **assistant-ui（MIT）** | React✓ + **shadcn 主题**（实朴前端就是 tailwind4+shadcn/radix），可组合 primitives（Thread/Message/Composer） | 只拿聊天 UI 组件层 | 小：可只取 primitives 自己接 SSE | 低-中 | ✅ 前端可选加速件（非必须） |

（来源 [S9]–[S20]）

**横向结论**：这个需求的「编排复杂度」其实很低——单 agent、3 个工具、多轮澄清、无 DAG、无并行角色。所有多 agent 框架在这里都不挣钱；框架的价值要到「多能力组合任务/真正的多角色协作」（路线图第三阶段）才出现。

---

## 3. 与实朴现有架构的契合度分析（仓库摸底实录）

### 3.1 后端：出图能力已经是「现成的工具」

摸底确认（`image-code/src/design_hub/`，六边形分层 interface/application/domain/ports/infrastructure 齐整，`composition.py` 唯一组装根）：

- **三个出图端点即三个工具**，且全部异步化：校验过即入队返回 `{"job_id"}`，天然适配「对话里先应答、图片再逐张流入」：
  - `POST /listing/generate`：`upload_ids(1..3)`、`prompt`(必填)、`ratio(1:1|3:4|9:16|16:9)`、`n(1..7)` XOR `plan({白底|场景|卖点}→张数, Σ3..10)`、`overlay_texts(≤2条×≤12字)`、`modifiers{platform(4值)|region(中国)|language(中文|英文)}`、`category(FOOD)`
  - `POST /listing/clone`：`product_upload_ids(==1)`、`reference_upload_ids(1..2)`、`clone_mode(参考风格|高度复刻→卡侧已改「完全复刻」待同步)`、`ratio`、`prompt`(选填)
  - `POST /listing/edit`：`source_image_key`、`prompt`(必填)、`edit_mode(delta|full)`、ratio 继承规则严格
  - 域值越界统一路由层 fail-fast 400（ISSUE-0024 口径）——**对话 agent 填错参数会被现有校验立刻打回，这正是我们要的防线**。
- **SSE 已是全套模式**：`GET /listing/{job_id}/events` 命名事件流（`task_started→model_called→逐张 image_generated{url,seed,image_type}/image_failed→task_completed{total_cost}|task_failed`），`InMemoryEventBus` 先回放历史再推实时（晚订阅不丢）。对话页的出图卡片可以原样复用这条流。
- **单进程契约**：`InProcessTaskQueue` = `asyncio.create_task` 进程内跑；对话编排器同样作为进程内组件加入即可，**不需要任何新中间件，Redis 铁律无碰撞**。
- **钱和闸门自动继承**：对话工具的服务端实现走现有 application 层（`ListingService`/commands），`CostGuard`（预扣/回滚/对账 + 三红线）与 `UserRateLimiter`（5 单/分 + ≤2 in-flight → 429）在同一路径上，**对话入口无法绕过成本与频控**——这是「工具=复用现有链路」相对「另起出图链路」的决定性优势。
- **鉴权**：JWT 依赖注入（`get_current_user`），SSE 有 `?access_token=` 变体（ISSUE-0011），`/chat` 路由与 chat-SSE 直接挂同一依赖即可，owner 隔离（非本人 404）沿用。
- **文本 LLM 现状：零**。全仓无任何 chat/completions 调用（`settings.py` 的 `dashscope_key` 是无引用死配置；`infrastructure/vision/` 已清空）。需要新增一个 **TextLLMPort（ports/）+ OpenAI 兼容 chat 适配器（infrastructure/providers/）**——和现有 `OpenAICompatImageProvider`（httpx、超时/退避仅限 I/O、多 key 轮询、`trust_env=False`）完全同构，六边形不破。

### 3.2 前端：不是 Next.js，但自建聊天页的零件都在

- React 19.2 + Vite 8 + TS + react-router-dom 7（组件式路由）+ zustand 5 + react-query 5 + tailwind 4 + shadcn/radix + motion 12；**DeerFlow/CopilotKit 的 Next.js 应用壳都不能直接搬**。
- SSE 客户端 = 原生 `EventSource`（`useListingEvents()`，命名事件逐类型 addEventListener），已解决 token 传递与终态关闭；聊天流可以复刻同一模式（或对话回复 MVP 先整段返回，后续再流式）。
- `ResultGallery` 的「按 image_type 分组、逐张点亮、失败槽、基于此图再编辑」交互可以封装成会话内的 JobCard 复用。
- **历史彩蛋**：`image-web/docs/出图工作台-合并设计.md` 里旧版 GenerateStudio 就是「大聊天框 hero」参照美图设计室的设计，后随世界 A 收敛为结构化表单退场——说明这个产品形态在本项目有过共识雏形，现在是带着 agent 能力回归，不是从零发明。
- 视觉：全站已定稿 Style 4「Glass SaaS」（浅灰底+玻璃白卡+单一紫 accent），自研动效组件（AuroraBackground/BorderBeam/MagicCard 等）现成——对话入口 hero 完全够「大胆点睛」的素材库。

### 3.3 提示词体系：对话 agent 的产出必须收敛为「现有契约的参数」

宪章+卡+物化块体系（`image-prompt/` 六类卡 → `prompt_composer.py` 逐字常量 + Registry + pytest 逐字闸）是质量的唯一杠杆，**对话层设计的第一原则：agent 永远不直接产 prompt 给图像模型，只产 /listing 请求体字段**：

- agent 澄清出的东西 = `plan/ratio/overlay_texts/modifiers/clone_mode/edit_mode` + **`prompt` 字段的用户自由文本**。其中「帮写」（把用户口语需求润成好的 `prompt` 字段，即美图接 DeepSeek R1 做的那件事）本来就是现有契约内的合法输入，经 `compose_prompt` 与品类保真块/图型卡组装——**卡体系一个字节都不绕过**。
- 与 ISSUE-0006（提示词体系演进为「宪章+卡+agent 组装」）的关系：那是**提示词生产侧**的远期演进（LLM 替代确定性拼接），本调研是**用户交互侧**的对话入口，两者独立、互不阻塞；远期宪章可以部分复用为对话 agent 的 system prompt 素材。
- ⚠️ 前置事项：卡↔code 同步闸当前有一处红（复刻卡已改「完全复刻」三贴一隔，code 仍为「高度复刻」，`test_clone_blocks_match_card` FAILED，dev 在飞）——clone 工具接入对话前该同步必须收口。

### 3.4 文本 LLM 选型（对话 agent 的大脑）

| 选项 | 定价（每百万 token） | 工具调用 | 大陆可用性 | 备注 |
|---|---|---|---|---|
| **DeepSeek 官方 V4-Flash**（推荐） | 输入 $0.14（缓存命中 $0.0028）/ 输出 $0.28 | ✅ 原生 Tool Calls + JSON Output | ✅ 直连、人民币、可开票 | 1M 上下文；**同时提供 OpenAI 兼容与 Anthropic 兼容两种端点**；旧名 deepseek-chat/reasoner 2026-07-24 弃用（映射 V4-Flash 两模式），接入直接用新名 [S21] |
| 通义千问 qwen3.5-plus / flash | plus ¥0.8 / ¥2；flash 低至 ¥0.2 输入 | ✅ function calling | ✅ 直连（阿里百炼） | 若未来重启千问 image，可共账号；batch 5 折 [S22] |
| Claude（经中转）Haiku 4.5 / Sonnet 4.6 / Opus 4.8 | $1/$5、$3/$15、$5/$25 | ✅（tool use 业界口碑最好） | ⚠️ 无官方大陆结算，**经 apinebula 可用** | 模型 ID：claude-haiku-4-5 / claude-sonnet-4-6 / claude-opus-4-8；SSE 流式、prompt caching（读≈0.1×）[S23] |
| apinebula（现有图像中转站）中转文本模型 | 倍率未验证（开放问题） | 视上游 | ✅（支付宝、大陆直连，宣称不存对话内容） | 官方明确中转 **Anthropic + OpenAI 系模型**——即**现有供应商就能供文本模型**，省一次新供应商进件 [S24] |

**成本量级测算**（按一次完整澄清会话 ≈ 6–10 轮、累计 ~40K 输入 + 4K 输出 token 估）：

- DeepSeek V4-Flash：≈ $0.007 ≈ **¥0.05/会话**（多轮共享前缀命中缓存后更低）
- qwen3.5-plus：≈ ¥0.04/会话
- Claude Haiku 4.5：≈ $0.06 ≈ ¥0.43/会话；Sonnet 4.6 ≈ ¥1.3/会话
- 对照：一套图 5 张真实成本 ≈ $0.25 ≈ ¥1.8（系统计价 ¥0.40/张=¥2.0）

**建议**：默认 **DeepSeek V4-Flash 官方直连**（对话成本 ≈ 图成本的 3%，可忽略；美图同款供应商，大陆合规链路最顺）；TextLLMPort 做成可切换后，用 apinebula 中转的 **Claude Haiku/Sonnet 做质量对照实验**（若澄清质量/工具调用可靠性有肉眼差距再谈升级）。千问作为「同集团备胎」。**不引 litellm，沿用「对 OpenAI 兼容协议编程 + base_url 可换」的既有先例。**

---

## 4. 落地方案 A/B/C 详设与推荐

### 方案 A：整接 DeerFlow 改造（❌ 不推荐）

- **做法**：fork deer-flow（v1 或 v2），删研究管线，把出图端点包成它的 tools/MCP，前端要么双前端并存要么把 Next.js 聊天页重写进 SPA。
- **新增依赖/服务**：v2 = Gateway + runtime + 沙箱 + 第二前端 + 第二 nginx 配置族；v1 = langchain/langgraph/litellm 全家 + Next.js。
- **与单进程架构兼容性**：差。v2 本身就是多服务；即便 v1，也要在两个进程间转发 JWT、跨服务保 CostGuard/频控语义（否则对话入口成为绕闸旁路）。
- **改动面**：后端「接」少「删改」多（五角色节点、Plan 模型、研究工具全拆）；前端等于重写。
- **量级**：20+ 人日起步，且 fork 维护是长尾（上游 v1→v2 已示范过「完全不共享代码」的重写）。
- **风险**：违反三条仓规（无谓依赖、复用优先不造新链路、litellm 先例）；运维面翻倍撞上 image-ops 单机双容器现状。

### 方案 B：轻框架只取编排层，嵌入现有 FastAPI（⚠️ 备选/升级路径）

- **做法**：`pydantic-ai`（首选，pydantic 已是核心依赖、类型化工具定义、原生 OpenAI 兼容/DeepSeek provider）或裸 `langgraph`（InMemorySaver，无 Redis）作为**进程内库**使用；新增 `interface/api/routes/chat.py` + `application/chat/`，工具函数直调 `ListingService`。
- **新增依赖**：pydantic-ai-slim(+provider) 或 langgraph+langchain-core；**无新服务**。
- **改动面**：后端 = 新路由 + 新 application 子包 + TextLLMPort/适配器（框架接管 loop 与流式）；前端与方案 C 相同（自写 /chat 页）。
- **兼容性**：好（进程内、异步、无外部状态存储）。
- **量级**：10–15 人日（比 C 多出框架学习/驯化与版本跟随）。
- **风险**：框架 churn（pydantic-ai 演进快，接入前需核版本；langgraph 1.x 稳定但带 langchain 依赖树）；对当前「单 agent+3 工具」的复杂度是超配。
- **何时启用**：路线图第三阶段出现真实的多步编排（组合任务、并行子任务、人审节点）时，把方案 C 的编排器内核换成它——只要 C 阶段把「编排器」隔离在 application 层、工具面与 SSE 契约不变，这个替换是开闭的（SOLID 正好要求我们这么分层）。

### 方案 C：零框架 tool-use 循环 + 自写聊天面板（✅ 推荐）

**后端**（全部进程内，六边形各归其位）：

| 层 | 新增物 | 说明 |
|---|---|---|
| ports/ | `TextLLMPort`（chat + tool-call 抽象） | 对协议编程，镜像 `model_provider.py` 的做法 |
| infrastructure/providers/ | OpenAI 兼容 chat 适配器 | httpx（已有依赖）；base_url/model/key 走 settings；超时/退避仅 I/O 域；DeepSeek 官方或 apinebula 均可指 |
| application/chat/ | `ChatOrchestrator`（tool-use 循环）+ 工具定义 | 循环：用户消息→LLM(带工具 schema)→若 tool_call→参数校验→**进程内调用现有 ListingService 命令链**（CostGuard/频控/账本自动生效）→把 `job_id` 与结构化结果回给 LLM→LLM 生成给用户的答复。工具集：`generate_listing_set` / `clone_reference` / `edit_image`（三者参数=现有请求体字段）+ `ask_user`（澄清收口用，可选） |
| interface/api/routes/ | `chat.py`：`POST /chat/messages`（同步返回或 SSE 流式答复）+ 会话查询 | 挂 `CurrentUserDep`；LLM 流式答复用与 listing 相同的 `text/event-stream` 命名事件风格 |
| 会话状态 | **MVP 内存字典 + TTL**（与 InMemoryEventBus 同级的进程内状态） | 重启丢会话=已接受的现有语义；**持久化后置**（建表触发「DB 先问用户」铁律，届时单独立项） |

要点：
- **出图不换轨**：对话里出的每一单都是正常 `listing_job`（历史页可见、可再编辑、计费一致）；对话层只负责把口语需求收敛成合法参数。
- **fail-fast 贯穿**：LLM 给的参数直接过现有 400 校验；校验失败把错误文本回喂 LLM 自纠一次，仍失败则如实告知用户（不静默兜底）。
- **图片流不经 LLM**：工具返回 `job_id` 后，前端用现有 `useListingEvents(job_id)` 直连 job SSE 逐张点亮——LLM 不需要等图、不为图付 token。

**前端**：

- 新受保护路由 `/chat`「对话创作」：空态 hero（大输入框 + 快捷卡），会话态为消息流；`ChatComposer` 支持贴图上传（复用 `POST /uploads` + `ImageUploader`）。
- 会话内 `JobCard`：内嵌 `ResultGallery` 槽位逻辑 + `useListingEvents`，套图在气泡里逐张点亮，失败张失败槽，成功张带「基于此图继续改」（把 edit 上下文回注对话）。
- 澄清答复附 quick-reply chips（比例/平台/张数按钮），少打字。
- 可选加速件：assistant-ui 的 Thread/Composer primitives（shadcn 主题，与现栈同族）；但现有 shadcn+motion 零件自写也就 2–3 天量级，倾向自写保 Style 4 一致性。

**新增依赖/服务**：后端 **0 新依赖、0 新服务**（httpx/pydantic 已有）；前端 0–1 个 UI 库（可 0）。
**量级**：8–12 人日（后端循环+工具+SSE 4–6；前端 3–4；联调+QA 回归 1–2）。
**风险**：自写循环的边界情形（并行 tool_call、畸形参数、上下文截断）需自担——但工具只有 3 个、参数域全部有服务端硬校验，且这正是 fail-fast 风格最好落的地方。

### 推荐理由汇总（C > B ≫ A）

1. **复杂度对齐**：需求本质是「澄清→构造请求→复述结果」，单 agent + 3 工具足够；框架价值在这里为负（依赖、驯化、churn）。
2. **仓规全绿**：无 Redis、无新服务、无 litellm、复用出图链路与闸门、SOLID 分层（Port 隔离让未来换模型/换框架都是开闭修改）。
3. **先例一致**：与 `OpenAICompatImageProvider` 的「对协议编程、中转站解耦、多 key 轮询」一脉相承，团队心智零迁移。
4. **成本可控**：DeepSeek 对话成本 ≈ 图成本 3%，且频控/红线自动覆盖对话触发的出图。
5. **可演进**：编排器藏在 application 层，第三阶段若真要多 agent，再评估 Pydantic AI/LangGraph 只换内核。

---

## 5. UI 层落地建议（对标截图那种入口）

### 5.1 信息架构：并存，不替代

- **MVP：`/chat` 作为新增一级入口**（导航「对话创作」tab），工作台三页（套图/复刻/编辑）原样保留为「专业模式」。理由：现有真实用户（美工）已习惯表单式精确控制，套图 plan/overlay 这种结构化参数表单效率更高；对话入口先服务「不会配参数」的新手与「懒得配」的快手场景。
- **首屏归属后置决策**：跑 2–4 周对话入口的采用率/完单率后，再决定是否把 `/` 首屏换成美图式对话 hero（把工作台挪为二级）。**不建议 MVP 就替换首屏**——软发布期用户少，别一次动两个变量。
- **双向逃生门**：对话澄清出的参数一键「带入工作台」（写入 zustand workbench-store 预填表单）；反向，表单页放「不确定怎么配？和 AI 聊聊」入口。这是表单与对话最健康的共生关系。

### 5.2 入口页组成（对齐美图形态，按实朴能力裁剪）

- **中央大输入框**：「和我聊聊，你想做什么图？」+ 支持直接拖图（先传图后说话是电商用户的自然顺序）。视觉用 Style 4 玻璃卡 + AuroraBackground/BorderBeam 点睛（符合「大胆但精选 2–4 个重磅配饰」的既有审美方针）。
- **分类快捷卡 = 预填首条消息的模板入口**。美图 6 类（电商设计/海报/视频/社媒/品牌/办公）里实朴现阶段只覆盖电商图，照抄会变成空承诺；建议按自家三能力+高频场景出 4–6 张卡：
  - 「商品套图」→ 预填：帮我给这个产品出一套主图（白底+场景+卖点）
  - 「爆款复刻」→ 预填：参考这张爆款图的风格给我的产品出图
  - 「改图/二次编辑」→ 预填：这张图帮我改一下…
  - 「卖点文案图」→ 预填：突出「买一送一」做两张卖点图（示范 overlay_texts）
  - （占位卡「更多品类 敬请期待」承接 FOOD 之外的品类扩展）
- **「AI 团队」按钮：不做进 MVP**。它在美图语境里是多 agent 团队的营销化呈现；实朴对应物是第三阶段的多角色编排（见 §6），MVP 放一个不可点的东西只会伤信任。

### 5.3 会话中的生成体验

- 出图以 JobCard 形式出现在 agent 气泡内：逐张点亮（现有 SSE）、单张失败显示失败槽与原因、完成后显示本单花费（`task_completed.total_cost` 现成）。
- 每张成功图挂动作条：下载 / 基于此图再编辑（对话内继续）/ 去历史页看大图。
- 澄清阶段控制在 1–2 轮以内出首稿（美图的体验基准是「一句话也能先出再调」）：参数缺省时 agent 用默认套图 plan（1/2/2=5 张）先问确认再执行，而不是无限追问。

---

## 6. 分期路线（MVP → 完整）

| 阶段 | 内容 | 量级 | 出口判据 |
|---|---|---|---|
| **P0 前置** | ① 复刻卡「完全复刻」卡↔code 同步收口（红闸转绿）② 选定文本 LLM 并开好账号/key（DeepSeek 直连；apinebula 文本倍率顺手验证）③ 与 PM 对齐入口定位与快捷卡文案 | 1–2 人日 | pytest 卡闸全绿；chat key 可调通 |
| **P1 MVP** | 方案 C 全量：TextLLMPort+适配器、ChatOrchestrator+3 工具、/chat 路由（LLM 答复 SSE）、内存会话、前端 /chat 页（hero+快捷卡+JobCard+quick-reply）、QA 回归（含「对话触发的单走同一频控/红线」用例） | 8–12 人日 | 内部灰度：美工用对话完成一套图+一次复刻+一次改图全流程 |
| **P2 增强** | 帮写强化（prompt 字段润色的专用指令）、edit 链对话上下文（「再亮一点」接上一单）、会话持久化（**触发 DB 亲签铁律，先问用户**）、对话内容安全审核接入（与 PRD 7.B 合并做）、免费额度/积分制对接后的对话内余额提示 | 5–8 人日 | 真实用户对话完单率、澄清轮数中位数达标 |
| **P3 编排升级** | 组合任务（「套图+按这套再复刻两个渠道版本」）、多角色呈现（此时才谈「AI 团队」）、评估把编排内核换 Pydantic AI/LangGraph、首屏是否切换对话 hero 的数据决策 | 另行立项 | P2 数据说话 |

---

## 7. 风险与开放问题

1. **内容安全（最高优先）**：对话入口把自由文本面从「prompt 字段」扩大到「开放聊天」，而 PRD 7.B（AIGC 审核+AI 标识）目前零实现。MVP 必须限定为登录用户内测/白名单灰度，公开放量前 7.B 是硬前置。
2. **备案卡点不因此改变**：toC 公网入口仍卡 sepaitech.com ICP 备案（现走 IP+自签证书），对话入口不影响也不解决这件事，别把两条时间线混在一起。
3. **apinebula 文本模型倍率未验证**：站点确认中转 Anthropic+OpenAI 系文本模型，但 Claude/GPT 文本档的实际计价倍率与稳定性需实测（开放问题，P0 顺手做）；DeepSeek 走官方直连不受此影响。
4. **模型命名windows期**：DeepSeek 旧名 deepseek-chat/reasoner 2026-07-24 弃用，接入直接用 deepseek-v4-flash 新名，避免上线即改名。
5. **会话状态易失**：MVP 内存会话=进程重启丢上下文（与现有 EventBus 同语义）。可接受，但要在 UI 上「新会话」显式化；持久化涉及建表，**必须先征求用户意见**（DB 铁律）。
6. **LLM 参数幻觉**：靠三层防：工具 schema 枚举收紧（中文枚举原样进 schema）→ 服务端 400 fail-fast → 错误回喂一次自纠；绝不静默改写用户意图。
7. **成本滥用面**：对话本身便宜，但对话可触发出图；现有 UserRateLimiter（5 单/分+≤2 in-flight）与三红线自动覆盖，另建议加「单会话出图单数上限」这一层对话侧闸。
8. **框架世界的 churn**：若走 B，pydantic-ai 版本 API 需在实施时点核（本调研未锁定其当前版本号）；AI SDK v6 wire format 刚大改——这两条都强化了 C 的「自有协议自有 SSE」选择。
9. **竞品动态**：美图设计室电商 Agent 已做到「一句话生成主图/副图/详情页整套方案」且月活 ~1800 万、月产电商物料 4000 万+ [S25][S26]；实朴的差异化仍是「品类保真卡体系+不过分修改」的质量路线，对话入口是补齐交互代差，不是抄它的广度。

---

## 8. 来源链接

**DeerFlow**
- [S1] bytedance/deer-flow GitHub（README，2.0.0 SuperAgent harness、MIT、~75.8k stars；本次 WebFetch 摘要）：https://github.com/bytedance/deer-flow
- [S2] deer-flow 中文 README（v1 架构：FastAPI+Next.js+conf.yaml/litellm）：https://github.com/bytedance/deer-flow/blob/main/README_zh.md
- [S3] DeerFlow 2.0 解析（v1→v2 重写、lead agent+sandbox+skills、main-1.x legacy 分支）：https://dev.to/arshtechpro/deerflow-20-what-it-is-how-it-works-and-why-developers-should-pay-attention-3ip3
- [S4] 字节 DeerFlow 2.0 深度解析（知乎，2026-03 更新）：https://zhuanlan.zhihu.com/p/2023363357256819250
- [S5] DeerFlow 2.0 使用指南（apidog，2026）：https://apidog.com/blog/deer-flow-guide-2026/
- [S6] DeerFlow v1 多智能体工作流（DeepWiki）：https://deepwiki.com/bytedance/deer-flow/2.1-multi-agent-workflow
- [S7] v1 本地部署实录（五角色/conf.yaml/server.py:8000）：https://blog.csdn.net/Guo_Python/article/details/148080566
- [S8] ByteDance DeerFlow 框架解析（Medium）：https://medium.com/data-science-in-your-pocket/bytedance-deerflow-multi-ai-agent-framework-for-deep-research-acfbc4d90fbd

**备选 harness**
- [S9] LangGraph 1.0 GA 公告（2025-10，MIT，API 稳定承诺）：https://changelog.langchain.com/announcements/langgraph-1-0-is-now-generally-available
- [S10] LangChain/LangGraph 1.0 里程碑：https://blog.langchain.com/langchain-langgraph-1dot0/
- [S11] LangGraph 持久化/检查点（InMemorySaver/SqliteSaver，无需 Redis）：https://docs.langchain.com/oss/python/langgraph/add-memory
- [S12] Vercel AI SDK 6（Apache-2.0）：https://vercel.com/blog/ai-sdk-6 与 https://github.com/vercel/ai
- [S13] AI SDK 流协议（自定义后端/FastAPI）：https://ai-sdk.dev/docs/ai-sdk-ui/stream-protocol
- [S14] AI SDK + FastAPI 官方模板：https://vercel.com/templates/next.js/ai-sdk-python-streaming
- [S15] CopilotKit（React agent UI、AG-UI 协议）：https://github.com/copilotkit/copilotkit 与 https://www.copilotkit.ai/ag-ui
- [S16] CopilotKit×LangChain/FastAPI 集成文档：https://docs.langchain.com/oss/python/langchain/frontend/integrations/copilotkit
- [S17] pydantic/pydantic-ai（类型安全 agent 框架、多 provider）：https://github.com/pydantic/pydantic-ai 与 https://ai.pydantic.dev/models/overview/
- [S18] 2026 agent 框架横评（provider-native vs 独立框架取舍）：https://www.morphllm.com/ai-agent-framework
- [S19] 开源 agent 框架对比（Langfuse）：https://langfuse.com/blog/2025-03-19-ai-agent-comparison
- [S20] assistant-ui（MIT，React/shadcn 聊天 primitives）：https://github.com/assistant-ui/assistant-ui

**文本 LLM 与中转**
- [S21] DeepSeek 官方定价与模型（V4-Flash/Pro、OpenAI+Anthropic 双兼容端点、Tool Calls、2026-07-24 旧名弃用）：https://api-docs.deepseek.com/quick_start/pricing
- [S22] 通义千问 2026 定价整理（qwen3.5-plus ¥0.8/¥2 等）：https://developer.aliyun.com/article/1714977 与 https://developer.aliyun.com/article/1713523
- [S23] Claude 当前模型与定价（Haiku 4.5 $1/$5、Sonnet 4.6 $3/$15、Opus 4.8 $5/$25；tool use/SSE）：https://platform.claude.com/docs/en/about-claude/models/overview （经 claude-api 参考包核对，缓存 2026-06）
- [S24] APINebula（大陆直连中转，Anthropic+OpenAI 系统一接入、支付宝）：https://apinebula.com/ 、https://docs.apinebula.com/docs/quickstart 、评测 https://www.bestzhuji.com/chatgpt/9285.html

**竞品（美图设计室）**
- [S25] 美图发布 AI Agent（RoboNeo「一句话搞定影像生产力」）：https://www.meitu.com/zh/media/419
- [S26] 美图设计室推出电商设计 Agent（一句话生成主图/副图/详情页）：https://www.pingwest.com/a/309407
- [S27] 美图设计室接入 DeepSeek R1 帮写（自定义描述智能生成）：https://www.pingwest.com/a/302562
- [S28] 美图设计室 Agent 生图教程（首页对话框入口形态）：https://www.designkit.cn/article/astjcxsrmzn20251014
- [S29] 一句话生成商品套图（知乎）：https://zhuanlan.zhihu.com/p/1977394340046337723

**仓内佐证（摸底实录）**
- 后端契约与分层：`image-code/src/design_hub/interface/api/routes/listing.py`、`interface/listing_schemas.py`、`application/listing/{commands,prompt_composer}.py`、`application/cost/{guard,budget}.py`、`infrastructure/{queue/in_process,events/memory,providers/openai_compat}.py`、`interface/api/{deps,throttle}.py`
- 前端栈与交互：`image-web/package.json`、`src/api/listing.ts`、`src/pages/WorkbenchPage.tsx`、`src/components/listing/ResultGallery.tsx`
- 提示词体系：`image-prompt/00-charter.md`、`image-prompt/{category,image-type,clone-mode,edit-mode}-cards/`、`image-code/tests/test_prompt_cards.py`
- 历史设计与规划：`image-web/docs/出图工作台-合并设计.md`（旧「大聊天框」设计，已退场）、`image-issues/ISSUE-0006-提示词体系演进为宪章+卡+agent组装.md`、`image-prd/2026-05-27-design-platform-prd.md` §B4（拒绝 LiteLLM 先例）与 §7.A/B/D（备案/内容安全/积分制 gate）、`竞品调研-designkit-美图设计室.md`
