# 设计中台 · 阶段 1 引擎核心 — 需求功能点分析（开发排期用）

| 项 | 内容 |
|---|---|
| 文档版本 | v1.0 |
| 编制日期 | 2026-05-28 |
| 范围 | PRD 阶段 1「图生图引擎」的后端引擎核心（模块 ①②③④⑥的引擎部分） |
| 用途 | 开发排期、工作量估算、依赖与关键路径分析 |
| 估算口径 | 1 名熟练后端工程师的有效工时（人天），已含 TDD 测试编写开销，未含会议/沟通损耗 |
| 排期前提 | 全程遵循 SOLID；CI 用 MockModelProvider 零真实 API 费用 |

> 配套实现依据：`image-prd/2026-05-27-design-platform-prd.md` §3 / §6，`image-prd/prompt-engineering-playbook.md`。
> 阶段 2 副驾驶链路（项目工作台 / 需求单 / 改稿单 / 客户档案 / 导出归档）不在本分析范围。

---

## 0. SOLID 总纲（贯穿全部功能点）

| 原则 | 在本引擎的落点 |
|---|---|
| **SRP 单一职责** | 每个词库、每个模板族、估算器、预算策略、注册表各自独立成文件/类，一个单元只有一个变更理由 |
| **OCP 开闭** | 路由表数据驱动；模板族、Provider、词库均可插拔注册。新增模型/模板族/合成方式 = 新增文件，**不修改**已有编排与路由代码 |
| **LSP 里氏替换** | `MockModelProvider` 与真实 Provider 行为契约一致，pipeline 与路由层对二者无差别调用 |
| **ISP 接口隔离** | `AbstractModelProvider` 仅暴露 `generate`；`VisionAssist`、`LedgerRepository` 接口最小化，实现方不被迫实现无关方法 |
| **DIP 依赖倒置** | `GenerationPipeline` 依赖抽象（Provider 注册表、Ledger 仓储接口、Router、Orchestrator 接口），具体实现由组装根注入 |

**排期含义**：因为 OCP/DIP，里程碑可解耦——脊柱（M1）先用 Mock 跑通，真实 Provider（M3）与两阶段合成（M4）作为新实现"插入"而非"改写"，三者可在 M1 完成后并行推进。

---

## 1. 功能点全景表

> 优先级：P0 = 引擎不可或缺；P1 = 完整度需要但可后置。
> 复杂度：S(简单) / M(中) / L(大，含外部不确定性)。

| 编号 | 功能点 | 模块 | 优先级 | 复杂度 | 估时(人天) | 里程碑 | CI 可零成本测试 |
|---|---|---|---|---|---|---|---|
| FP-A1 | 项目骨架（uv + FastAPI + SQLAlchemy async + 目录分层） | 基础设施 | P0 | S | 1.0 | M1 | ✅ |
| FP-A2 | 配置与密钥（Pydantic Settings + KMS 接口占位） | 基础设施 | P0 | S | 0.5 | M1 | ✅ |
| FP-A3 | 结构化日志 + fail-fast 异常基类（structlog） | 基础设施 | P0 | S | 0.5 | M1 | ✅ |
| FP-B1 | 领域枚举（SubScene/Tier/TemplateFamily/Style/Category/ModelName/MaterialType） | 领域层 | P0 | S | 0.5 | M1 | ✅ |
| FP-B2 | 领域 DTO（GeneratedImage/Brief/PromptPair/RoutingDecision/GenerationResult） | 领域层 | P0 | S | 0.5 | M1 | ✅ |
| FP-C1 | `AbstractModelProvider` 抽象接口（ISP） | Provider 适配 | P0 | S | 0.5 | M1 | ✅ |
| FP-C2 | `MockModelProvider`（可控延迟/失败率，CI 零费用） | Provider 适配 | P0 | M | 0.5 | M1 | ✅ |
| FP-C3 | `ProviderRegistry` 注册表（DIP 组装根） | Provider 适配 | P0 | S | 0.5 | M1 | ✅ |
| FP-C4 | Provider 异常体系（ProviderError/ProviderTimeout） | Provider 适配 | P0 | S | 0.25 | M1 | ✅ |
| FP-D1 | 路由表（模板族×档位，数据驱动可热更） | 模型路由 | P0 | M | 0.5 | M1 | ✅ |
| FP-D2 | `ModelRouter`（族+场景+档位→决策，含真人族强制 GPT 规则） | 模型路由 | P0 | M | 1.0 | M1 | ✅ |
| FP-D3 | fallback 同档位备选链生成（绝不跨档升级） | 模型路由 | P0 | S | 0.5 | M1 | ✅ |
| FP-E1 | 5 词库（色卡 A/负面 B/防御 C/质量 D/镜头 E） | Prompt 编排 | P0 | M | 1.0 | M1 | ✅ |
| FP-E2 | 模板族骨架基类 + 4 族（族 3/4/5/7） | Prompt 编排 | P0 | L | 1.5 | M1 | ✅ |
| FP-E3 | 10 条通用法则注入器（定调前置/独立文字段/质量收尾等） | Prompt 编排 | P0 | M | 1.0 | M1 | ✅ |
| FP-E4 | 视觉理解辅助（`VisionAssist` 接口 + Mock；真实 qwen-vl-max 后置） | Prompt 编排 | P0 | M | 0.5 | M1 | ✅ |
| FP-E5 | 虚构品牌名生成（按品类出 2-3 候选英文名+短句） | Prompt 编排 | P1 | S | 0.5 | M1 | ✅ |
| FP-E6 | `PromptOrchestrator` 编排器（填槽→防御→负面→质量→后处理） | Prompt 编排 | P0 | L | 1.5 | M1 | ✅ |
| FP-F1 | `CostEstimator` 成本预估（候选数×单价） | cost-guard | P0 | S | 0.5 | M1 | ✅ |
| FP-F2 | `BudgetPolicy` 3 条红线校验 | cost-guard | P0 | M | 0.5 | M1 | ✅ |
| FP-F3 | `LedgerRepository` 接口 + 内存实现（真实 PG 实现见 FP-H1） | cost-guard | P0 | M | 0.5 | M1 | ✅ |
| FP-F4 | `@cost_guard` 装饰器（预扣额度 + 失败回滚） | cost-guard | P0 | M | 0.75 | M1 | ✅ |
| FP-F5 | 出图前成本预估提示（结构化响应给前端） | cost-guard | P1 | S | 0.25 | M1 | ✅ |
| FP-G1 | `GenerationPipeline` 编排（route→prompt→estimate→guard→generate→fallback） | 任务流 | P0 | L | 1.0 | M1 | ✅ |
| FP-G4 | 多候选生成（默认 6 / 硬上限 12） | 任务流 | P0 | S | 0.5 | M1 | ✅ |
| FP-J1 | 单元测试套件（随 TDD 各功能点内联） | 测试 | P0 | — | 内联 | M1 | ✅ |
| FP-J2 | 集成测试（MockProvider 端到端跑通 pipeline） | 测试 | P0 | M | 0.5 | M1 | ✅ |
| FP-J3 | CI 流水线（ruff + mypy + pytest，零 API 调用） | 测试 | P0 | S | 0.5 | M1 | ✅ |
| FP-H1 | SQLAlchemy ORM（GenerationJob/GeneratedImage/ModelConfig/CostLedger） | 持久化 | P0 | M | 1.5 | M2 | ✅(测试库) |
| FP-H2 | Alembic 迁移 | 持久化 | P0 | S | 0.5 | M2 | ✅ |
| FP-G2 | arq 异步队列接入（任务入队/出队/死信） | 任务流 | P0 | M | 1.5 | M2 | 🟡 需 Redis |
| FP-G3 | SSE 进度推送（arq→Redis Pub/Sub→FastAPI EventSource） | 任务流 | P0 | M | 1.5 | M2 | 🟡 需 Redis |
| FP-C5 | 真实 Provider×4（OpenAI / 千问·万相 / Seedream / 灵动） | Provider 适配 | P1 | L | 6.0 | M3 | ❌ 真实 API |
| FP-I1 | BiRefNet 抠图服务封装（本地，原像素保真） | 两阶段合成 | P0 | L | 2.0 | M4 | ❌ GPU/权重 |
| FP-I2 | 程序合成（透视/比例/智能放置，产品 PNG 叠加空场景） | 两阶段合成 | P0 | L | 3.0 | M4 | 🟡 部分可 |
| FP-I3 | 光影协调（接触阴影 + harmonization 模型） | 两阶段合成 | P0 | L | 3.0 | M4 | ❌ 模型 |
| FP-I4 | S4 多角度双路径调度（路径 A 两阶段 / 路径 B 兜底转人工） | 两阶段合成 | P0 | M | 1.5 | M4 | 🟡 部分可 |

---

## 2. 模块详解

### 模块 A：基础设施（M1）

| FP | SOLID 落点 | 依赖 | 验收标准 |
|---|---|---|---|
| A1 项目骨架 | 目录按职责分层（domain/providers/routing/prompt/cost/tasks），非按技术层堆 | 无 | `uv run python -c "import design_hub"` 通过；`uv run pytest` 可执行空套件 |
| A2 配置密钥 | DIP：`Settings` 用 `SecretStr`，KMS 拉取做成可替换的 `from_kms` 入口 | A1 | 开发用 `.env.development`（无真密钥）；生产路径预留 KMS，密钥不落盘 |
| A3 日志异常 | SRP：异常基类只表达"领域错误"，I/O 错误另立分支（fail-fast：非 I/O 不吞错） | A1 | structlog 输出 JSON；自定义异常按类型可区分；无 catch-and-ignore |

**约束（来自 CLAUDE.md）**：Python 仅用 `uv`（`uv run`/`uv add`，不用 `uv pip`，不手改 pyproject）；非 I/O 逻辑 fail-fast，不加重试/兜底/默认值掩盖；重试与降级仅允许出现在 I/O/网络（模型调用、抠图服务）。

### 模块 B：领域层（M1）

| FP | SOLID 落点 | 依赖 | 验收标准 |
|---|---|---|---|
| B1 枚举 | 9 族枚举**全部定义**（V1 仅实现 4 族），新增族无需改枚举——OCP | A1 | 枚举值与 PRD/playbook 一一对应；`StrEnum` 便于序列化 |
| B2 DTO | 不可变 `frozen` dataclass，作为各层之间的稳定契约 | B1 | `GeneratedImage(url,seed,latency_ms,cost)` 等结构与 PRD §6.3.2 一致 |

### 模块 C：Provider 适配层（M1 抽象 + Mock，M3 真实）

| FP | SOLID 落点 | 依赖 | 验收标准 |
|---|---|---|---|
| C1 抽象接口 | **ISP**：唯一抽象方法 `async generate(...)`；`name`/`unit_cost` 为类属性 | B2 | ABC 不可实例化；签名与 PRD §6.3.2 完全一致 |
| C2 MockProvider | **LSP**：返回结构与真实一致，支持注入 `fail_rate`/`latency_ms` 模拟故障 | C1 | 同种子可复现；可触发 `ProviderTimeout` 供 fallback 测试 |
| C3 注册表 | **DIP** 组装根：按 `ModelName` 注册/取用，pipeline 不 import 具体 Provider | C1 | 取不存在 Provider 抛明确异常 |
| C4 异常体系 | SRP：网络/超时类异常独立，区分"可 fallback"与"致命" | A3 | `ProviderTimeout` ⊂ `ProviderError`，pipeline 据此决定是否切备选 |
| **C5 真实 Provider×4**（M3） | **OCP**：每家 1 个文件实现 C1，注册即用，**不改**路由/编排 | C1,C3,A2 | 各 Provider 联调出图成功；同步 SDK 用 `asyncio.to_thread` 包装 |

> 真实 Provider 拆分：OpenAI(gpt-image-2) 1.5d / Dashscope(千问·万相) 2.0d / Volcengine(Seedream) 1.5d / 灵动 1.0d，含密钥与重试/超时联调。

### 模块 D：模型路由器（M1）

| FP | SOLID 落点 | 依赖 | 验收标准 |
|---|---|---|---|
| D1 路由表 | **OCP**：族→首选模型、档位→候选/精度 全为数据（dict/配置），可后台热更不改码 | B1 | 表项与 PRD §3.5 一致（族3→Seedream、族4→GPT、族5→Seedream、族7→千问） |
| D2 Router | SRP：路由只做"选模型"，不碰成本/生成 | D1 | 含真人/复杂版式族（1/2/6/8/9）强制 GPT-image 忽略档位；精修档升 GPT、草稿档降灵动/万相 |
| D3 fallback 链 | 业务规则显式化：同档位备选有序，**绝不自动跨档升级**（防烧钱） | D2 | 返回 `RoutingDecision(primary, fallbacks, candidate_count)` |

### 模块 E：Prompt 编排子系统（M1，质量命脉）

| FP | SOLID 落点 | 依赖 | 验收标准 |
|---|---|---|---|
| E1 5 词库 | **SRP**：每库一个类/文件（ColorLib/NegativeLib/GuardLib/QualityLib/LensLib），独立维护 | B1 | 词条与 playbook §四完全一致；缺失 key 抛错（fail-fast，不静默给默认） |
| E2 模板族骨架 | **OCP+LSP**：`TemplateFamilySkeleton` 基类 + 族3/4/5/7 子类，按 family 注册取用 | B1 | 每族 `required_slots()` 与 `render(slots)`，骨架与 playbook §三一致；缺槽报错 |
| E3 10 法则注入器 | SRP：每条法则一个纯函数，编排器按序套用 | E1 | 定调置首句、文字独立成段、质量词+比例收尾、防御词前置可验证 |
| E4 视觉辅助 | **ISP+DIP**：`VisionAssist` 接口（`async analyze(images)→ProductVisualInfo`）+ Mock | B2 | Mock 返回固定识别结果；真实 qwen-vl-max 作为另一实现注入（M3 附带） |
| E5 品牌名生成 | SRP：独立生成器，按品类出候选 | B1 | 族1/9 场景产出 2-3 个英文候选名+主标题短句 |
| E6 编排器 | **DIP**：编排器依赖"族注册表/词库/视觉接口/品牌生成器"抽象，组合而非继承 | E1-E5,D | 输出 `PromptPair(positive,negative)`；按目标模型做差异化后处理（GPT 中文比例 / MJ `--ar`） |

> E 模块是工作量与质量的重心（合计 ~6 人天），也是 SOLID 展示最充分处：新增模板族或词条不触碰编排器主流程。

### 模块 F：cost-guard 成本守门（M1 逻辑，M2 接 PG）

| FP | SOLID 落点 | 依赖 | 验收标准 |
|---|---|---|---|
| F1 估算器 | SRP：只算"候选数×单价"，不查预算 | B2,C1 | `estimate(decision, provider)→Decimal` |
| F2 预算策略 | SRP：3 红线为纯函数式校验，与存储解耦 | F1 | 单次>公司剩余50%→拒；用户已用≥配额→拒；公司已用≥总预算→拒 |
| F3 Ledger 仓储 | **DIP**：`LedgerRepository` 接口 + 内存实现；PG 实现（FP-H1）后续注入 | A1 | 内存实现支持 `reserve/rollback/get_*_month_used`，并发安全 |
| F4 `@cost_guard` | **OCP**：装饰器包裹生成入口，预扣→失败回滚，不侵入业务逻辑 | F1-F3 | 通过则预扣额度；被装饰函数抛异常则回滚（fail-fast 再抛出） |
| F5 预估提示 | SRP：组装 PRD §3.10 的结构化提示 | F1,F3 | 返回档位/候选数/模型/预估成本/本月已花费/预算 |

### 模块 G：出图任务流（M1 同步编排，M2 异步+SSE）

| FP | SOLID 落点 | 依赖 | 验收标准 |
|---|---|---|---|
| G1 Pipeline | **DIP 集大成**：注入 router/orchestrator/registry/estimator/cost_guard，编排但不实现细节 | C,D,E,F | 端到端：Brief→候选图列表；主模型失败按 D3 切备选；全失败抛错不跨档 |
| G4 多候选 | 业务规则：默认 6，>12 抛错 | G1 | 候选数受 `RoutingDecision.candidate_count` 与硬上限约束 |
| **G2 arq 异步**（M2） | **OCP**：Pipeline 不变，外面套 arq task 包装 | G1,H | 任务入队/重试/死信；worker 自暴露 `/metrics` |
| **G3 SSE**（M2） | SRP：事件发布与业务分离（task_started/model_called/image_generated/...） | G2 | Redis Pub/Sub→SSE；nginx `proxy_buffering off` |

### 模块 H：持久化（M2）

| FP | SOLID 落点 | 依赖 | 验收标准 |
|---|---|---|---|
| H1 ORM | 高频字段（风格/品类/物料/档位/模型）独立列，扩展用 JSONB | B,F3 | 4 实体表；`LedgerRepository` 的 PG 实现替换内存实现（LSP） |
| H2 Alembic | — | H1 | 迁移可 upgrade/downgrade |

### 模块 I：两阶段合成引擎（M4，命脉，高不确定性）

| FP | SOLID 落点 | 依赖 | 验收标准 |
|---|---|---|---|
| I1 BiRefNet 抠图 | **DIP**：`Matting` 接口 + BiRefNet 实现，pipeline 通过接口调用 | G1 | 白底图抠图近无损；产出透明 PNG |
| I2 程序合成 | SRP：合成器只管"叠加+透视+比例" | I1 | 产品像素 100% 来自原图；智能放置 |
| I3 光影协调 | **OCP**：接触阴影/harmonization 作为可插拔后处理步骤 | I2 | 前景配背景光，肉眼一致性 ≥95% |
| I4 S4 双路径 | SRP：调度器按"多角度/单角度"分流，单角度兜底不达标转人工 | I1-I3,C5 | 路径 A 走两阶段；路径 B 多视角模型 9-12 候选，全<4星转人工 |

> I 模块依赖 GPU、模型权重与真实造景 API，估时不确定性最高（合计 ~9.5 人天，建议预留 +30% buffer）。需在 M1 脊柱稳定、M3 真实 Provider 可用后启动。

### 模块 J：测试与 CI（M1）

| FP | SOLID 落点 | 依赖 | 验收标准 |
|---|---|---|---|
| J1 单测 | 随 TDD 内联，每功能点先写失败测试 | 全部 | 覆盖路由分支/编排填槽/红线/fallback |
| J2 集成 | LSP 验证：MockProvider 端到端跑通 | G1 | Brief→6 候选；故障注入触发 fallback |
| J3 CI | — | J1,J2 | ruff + mypy + pytest 全绿，零真实 API |

---

## 3. 里程碑排期

| 里程碑 | 内容 | 含功能点 | 工作量(人天) | 交付物 | 可独立验收 |
|---|---|---|---|---|---|
| **M1 架构脊柱** | 抽象+路由+编排+守门+同步 pipeline，Mock 端到端 | A,B,C1-4,D,E,F,G1,G4,J | **≈18** | CI 绿、Mock 跑通、SOLID 完整 | ✅ |
| **M2 持久化+异步** | ORM+迁移+arq+SSE | H,G2,G3 | **≈5** | 真实落库、异步出图、进度推送 | ✅ |
| **M3 真实 Provider** | 4 家模型对接 + qwen-vl 视觉 | C5(+E4 真实) | **≈6** | 真实出图、成本可量 | ✅ |
| **M4 两阶段合成命脉** | BiRefNet+合成+光影+S4 调度 | I | **≈9.5(+buffer)** | 一致性≥95%、可用率≥70% | ✅ |
| **合计** | | | **≈38.5 人天** | | |

**与 PRD 对照**：PRD 阶段 1 预估 1-1.5 月。单人串行 ≈ 8 周；双人在 M1 后并行（一人 M3 真实 Provider，一人 M4 合成）可压到 ≈ 5-6 周，符合 PRD 节奏。

### 3.1 关键路径

```
A1 → B1 → (C1 ∥ D1 ∥ E1)          [B1 是最早分叉点]
        C1 → C2,C3,C4
        D1 → D2 → D3
        E1 → E2,E3,E4,E5 → E6
   (C,D,E,F 完成) → G1 → G4 → J2 → J3        [G1 是汇聚点 = 关键路径终点]
M1 完成 ──→ M2(H,G2,G3)
        └─→ M3(C5)        ┐ M3、M4 可并行（OCP 解耦）
        └─→ M4(I)         ┘ 但 I4 需 C5 就绪
```

**关键路径**：`A1 → B1 → E1 → E2 → E6 → G1 → J2 → J3`（Prompt 编排是最长链，约 7 人天），其余分支（C/D/F）可与 E 并行。

### 3.2 并行机会

- M1 内：B1 完成后，**Provider(C)、路由(D)、编排(E)、守门(F) 四条线可并行**，瓶颈在编排 E（~6d）。两人协作时一人专注 E。
- M1 完成后：**M2 / M3 / M4 三里程碑解耦**，可三线并行（受人手限制）。这正是 OCP/DIP 解耦带来的排期收益。

### 3.3 排期风险与缓冲

| 风险 | 影响里程碑 | 缓冲对策 |
|---|---|---|
| 两阶段合成质量调参反复 | M4 | I 模块整体 +30% buffer；先用 200 张真实订单校准 |
| 真实 Provider SDK 差异/限流 | M3 | 同步 SDK 用 `asyncio.to_thread`；每家独立联调，互不阻塞 |
| 模型 API 单价变动 | M3/全局 | 单价配置化（ModelConfig），不硬编码进路由 |
| 编排器需求字段后续扩展 | M1(E) | 槽位用字典 + JSONB 扩展，骨架可版本化 |

---

## 4. 排期建议（单人节奏）

| 周 | 重点 | 里程碑 |
|---|---|---|
| 第 1 周 | A 基础设施 + B 领域 + C Provider 抽象/Mock + D 路由 | M1 前半 |
| 第 2 周 | E Prompt 编排（词库+4族+法则+编排器，重头） | M1 |
| 第 3 周 | F cost-guard + G1/G4 pipeline + J 集成/CI（M1 收尾验收）+ H 持久化起步 | M1→M2 |
| 第 4 周 | G2 arq + G3 SSE（M2 收尾）+ C5 真实 Provider 起步 | M2→M3 |
| 第 5-6 周 | C5 完成 + M4 两阶段合成（BiRefNet/合成/光影/S4） | M3+M4 |

> M1（脊柱）是其余一切的地基，**必须先做且做扎实**——它的 SOLID 边界决定 M2/M3/M4 能否"插入式"低成本扩展。

---

**文档结束。** 下一步：经确认后，对 M1 各功能点编写 bite-sized TDD 实施计划（writing-plans 产出）。
