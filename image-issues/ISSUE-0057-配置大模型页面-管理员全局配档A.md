---
id: ISSUE-0057
title: 「配置大模型」页面——管理员全局配 model_config + 通用中转 provider + 用户选模型（档 A）
status: 已确认        # 需求定稿(PRD §3.16+反转0017)+用户已签schema+拍A1,前置全清、无PM/用户阻塞；待coordinator排slot(0050批后)派dev+frontend-b开工
severity: P2          # 新特性（获客/灵活性 + 备用渠道切换=治 ISSUE-0056 单点的结构性解）；非阻断、非资损
reporter: 开发        # 用户 2026-07-07 经 dev 窗口提需求（盘点占位符时衍生），dev 出技术设计并路由 PM 立需求
owner: coordinator    # 前置全清(需求定稿+schema签+A1)；⚠️提级到0050前(用户点名#1044)=A/B线收口后即开工，纯排期无阻塞
created: 2026-07-07
related:
  - issue: ISSUE-0017（曾移除 qwen-image 出图模型——本条反转「其他模型不做」的范围决定，需 PM 记录）
  - issue: ISSUE-0056（apinebula 单一 key 挂→全站出图断；本条「可配备用渠道」附带缓解此类单点）
  - code: image-code config/showcase 无关；infrastructure/db/models.ModelConfig（现表）、interface/api/routes/admin（现 /admin/models）、
    application/registry.ProviderRegistry、infrastructure/providers/openai_compat.OpenAICompatImageProvider（拟泛化）、
    application/listing/listing_service.generate（现硬编码 ModelName.GPT_IMAGE_2）、composition.build_registry
  - 铁律: DB 设计先问用户（本条扩 model_config 表=DDL→用户签 schema 前不动手）
---

## 定性（用户 2026-07-07 提需求）
让平台可**灵活配置/启用多个出图模型**，用户按需选用。**起步 = 档 A：管理员全局配**（用户 2026-07-07 拍板 A/B/C 中选 A）。
- **档 A 口径**：管理者在 admin 页统一管「平台支持哪些模型 + 连接配置 + 单价 + 启用」，用户只是**选用**哪个已启用模型出图。**走平台 key、积分制不变**（非 per-user 自带 key）。
- 未选 **B（用户自带 key，per-user 加密存 key + 计费口径变）** 与 **C（混合）**：档 A 最贴现有 model_config、改动最小、安全面最低、最快上线。

## 现状（地基已铺一半）
- `model_config` 表（`name` PK / `unit_cost` / `enabled` / `extra` JSON）+ `/admin/models` GET·PUT（仅改 unit_cost/enabled）+ `ProviderRegistry`（LSP 干净，按 name 覆盖）本就为多模型可配设计。
- 但：`enabled` **未被消费**（路由用静态表、只注入 unit_cost）；只 `gpt-image-2` 接了真 provider（其 base_url/key/model 在 `.env`）；出图链 `listing_service.generate` **硬编码 `ModelName.GPT_IMAGE_2`**；Seedream/万相/灵动仅 Mock 枚举、无真 provider（ISSUE-0017 曾移除 qwen-image）。

## 技术设计（dev 提案）
1. **通用 OpenAI 兼容 image provider**：泛化现有 `OpenAICompatImageProvider`（已是「base_url + key + model + unit_cost」形状）——**不为每个模型写专属 adapter**，中转站/兼容模型填参即插即用。registry 按每行 enabled 的 model_config 实例化一个 provider。
2. **`model_config` 表升级为「模型注册表」**：每行 = 一个可用模型的**完整连接配置**（见下 schema 提案）。
3. **消费 `enabled` + 新增默认模型**：出图链去掉硬编码 GPT_IMAGE_2，改按「用户选的模型 / 默认模型」`registry.get(selected)`。禁用/未配的模型不可选。
4. **请求加可选 `model` 字段**：`ListingGenerateRequest`（及 clone/edit、chat 工具）加 `model: str | None`（默认=default-enabled）；launcher 校验 model 属已启用集合、否则 fail-fast 400。
5. **`/admin/models` 扩为完整 CRUD**：增删模型 + 改 base_url/model/cost/enabled/default。
6. **附带收益**：可配**备用渠道** → 主渠道（apinebula）挂时切备用，直接缓解 ISSUE-0056 单点故障。

## ⚠️ DB schema 提案（DDL·扩 model_config·**待用户签字**，铁律）
扩 `model_config`（现 name/unit_cost/enabled/extra）新增列：
- `provider_type` VARCHAR — adapter 选择器，默认 `openai_compat_image`。
- `base_url` VARCHAR — 中转站 endpoint。
- `model` VARCHAR — 传给上游 API 的模型 id。
- `is_default` BOOL — 出图默认模型（恰一个 true）。
- **密钥存储二选一（决定安全面，请用户拍）**：
  - **A1（dev 推荐）`api_key_env` VARCHAR**：DB 只存**环境变量名**，真密钥仍留 server `.env`（chmod600、不入库、不进群聊）——**密钥零入库、零加密负担、沿用现有 ops 供密**。代价：新增模型的 key 需 ops 在 .env 配一次（admin 页填 env 名引用）。
  - **A2 `api_key_cipher` VARCHAR**：密钥**加密后入库**，admin 页可直接填 key（免 ops）。代价：需引入对称加密（加密主 key 仍在 .env）+ 密钥入库=泄漏面、审计面更大。
- 现有 `enabled` 语义从「仅记录」升级为「真 gate 可用性」；`unit_cost`/`extra` 保留。
- **迁移**：`gpt-image-2` 现有行从 .env 值回填 base_url/model/provider_type/is_default=true；零数据丢失。走迁移轮（mysqldump 备份、可回滚）。

## 待办分工（签字/立需求后）
- **PM**：立需求/PRD——**反转 ISSUE-0017 范围**（改为「模型可配、按需接入」）+ 定 UX（admin 配置页 + 用户出图模型选择器）+ 关账口径 + 内测灰度不变。
- **用户**：① 签 DB schema；② 拍密钥存储 **A1（推荐）/ A2**。
- **dev（我）**：通用 provider 泛化 + model_config 扩展 + 消费 enabled + 出图链去硬编码 + 请求 model 字段 + admin CRUD + alembic 迁移（签字后）。
- **frontend-b**：admin 模型配置页 + 用户出图模型选择器。
- **QA**：验收（配置生效/禁用不可选/默认回退/备用渠道切换/零回归）。

## 范围外（YAGNI，二期）
- 档 B/C（用户自带 key、per-user 配置）——本条只做档 A。
- 上游自动故障切换编排（先支持手动配备用渠道，自动 failover 二期）。
- 非图像模型（文本 LLM 走独立 TEXT_LLM_* 配置，不并入本表）。

## 处理记录
- 2026-07-07 [dev] 用户经 dev 窗口提需求「做配置大模型的页面、让用户灵活配置需要的模型」；dev 给 A/B/C 分叉 + 技术建议（通用兼容 provider），
  **用户拍板档 A（管理员全局配、平台 key、积分制不变）**。dev 出技术设计 + DB schema 提案（含密钥存储 A1/A2）→ 路由 PM 立需求。
  status=待确认；owner=PM（立需求）。**开工前置**：① 用户签 DB schema + 拍密钥存储 A1/A2；② PM 立需求（反转 ISSUE-0017 范围）。DB 铁律=签字前 dev 不动表/迁移。
- 2026-07-07 [coordinator] 编排口径（#1009）：**排队位=0050 批之后**（P0 key→0052/0055/0056 收口→0050 时区批→0057），非阻断不抢档。
  三点定调：① 档 A 已用户拍板、PM 照此立需求；② **「渠道故障切换」升为一等公民写进需求**（非附带）——本条最大战略价值=治 ISSUE-0056 这类单点，
  下次中转站抖动管理员切渠道即恢复；③ 密钥存储 coordinator **倾向 A1**（env 引用、密钥不入库，避加密/轮转复杂度、与现行实践一致），理由带给用户拍板。
  **签字流程**：dev 的 model_config DDL 提案**等 PM 需求定稿后**由 coordinator 拿去给用户亲签（含 A1/A2 拍板），**签字前零动表**。@pm 立需求顺带记录 ISSUE-0017 范围反转。
- 2026-07-07 [dev] **用户亲签 DB schema + 拍密钥存储 A1**（用户直接回 dev「schema 签。密钥存储 A1。」）：
  → **DB 铁律闸已过**（对本条 §DB schema 提案的当前形态：扩 model_config + `provider_type`/`base_url`/`model`/`is_default`/`api_key_env`；
  **A1=密钥不入库、DB 仅存 env 变量名**、真 key 留 server .env）。⚠️ 若 PM 立需求把「渠道故障切换」做成一等公民而**新增/改动 schema 字段**
  （如 fallback 顺序列），该 delta 由 coordinator 再拿给用户确认（本次签字覆盖当前提案、增量另签）。**仍不立即开工**：0057 排 0050 批之后、待 PM 需求定稿 + slot。
  另：用户确认 **`openai_api_key` 死配置删**（已执行 `896fdde`，同 dashscope 类）、**mock 兜底保留**（本地联调基建、非死码）。
- 2026-07-07 [PM] **立需求定稿**（用户已亲签 schema+A1，签字轮省）：落 **PRD §3.16**（档 A 全设计 + 战略价值 + 已签 schema/A1 + UX + 验收 7 条 + 范围外 + 分工排队）+ **ISSUE-0017 范围反转记录**（forward-pointer，0017 保持已关闭；qwen 移除本身不回滚，变的是「不接其他模型」政策→注册表制；记忆 project_provider_scope_final 被超越）。
  **关键裁定——「渠道故障切换」一等公民不触发 delta 签字**：手动切换用**已签 schema 的 `is_default`/`enabled`** 即可（admin 在已配模型间切默认/启禁）→ **无新增字段、无需增量签字**；自动 failover（需 fallback 顺序字段=schema delta）明确划**范围外二期、届时另签**。故本立需求**未引入任何新字段、无 delta**（coordinator #1011 确认「直接按已签 schema+A1 写」）。
  **验收 7 条**（QA）：①admin 配置即时生效 ②用户选已启用/禁用不可选 ③非法 model→fail-fast 400 ④**备用渠道切换（主渠道故障→切备用→出图恢复）** ⑤默认回退正确 ⑥零回归（gpt-image-2 出图/计费/积分/历史+迁移零丢失）⑦密钥不泄漏（A1 只回 env 名）。
  status 待确认→**已确认**（需求定稿 + schema 签 + A1 拍，前置全清）；owner→coordinator（排 slot：0050 批后派 dev+frontend-b 开工）。DB 签字闸已过、**开工无 PM/用户阻塞**，纯排期。
- 2026-07-08 [PM] **⚠️ 排期提级（用户点名，coordinator #1044）**：0057 **提级到 0050 之前**——用户今天两次点名（波动配置查询工具 get_pricing_quota 读 model_config + 直接问「0057 去哪了」）= 明确需求信号；且其**「备用渠道切换」是 ISSUE-0056 类断供的结构性解**（提级有战略理由）。
  **新队列**：**A/B 线收口（今天）→ 0057 开工 → 0050 时区批 →（key 恢复插入即跑收口三连 0052/0055/0056）**。@dev A 线工具增量交付后**直接接 0057**（schema 已签/A1 已拍/PRD §3.16 封存、slot 到即上）；@frontend-b 0057 配置页 UI（admin 域新页）等 dev 后端契约出来接棒。前置仍全清、无 PM/用户阻塞、纯排期开工。owner=coordinator（派工）。
- 2026-07-08 [dev] **后端 MVP 三片全落**（提级后开工，备用渠道切换功能闭环=治 0056 单点结构性解）：
  ① DDL 底座 `1ca3830`：model_config +provider_type/base_url/model/api_key_env/is_default 五列（用户亲签 schema）+ 迁移
     `c9e4a1b73d52`（down=b3f8c1a24d90，sqlite up/down 实测干净；**迁移执行走 qa 先行+mysqldump 纪律、coordinator 从非 3225b6b 另编排**）。
  ② admin CRUD `a268a0a`：POST/GET/PUT/DELETE /admin/models + PUT …/default（事务保恰一默认=渠道切换）；**ModelConfigOut 只回 api_key_env
     env 名、绝无真 key 字段（验收⑦守死，单测断言）**；openapi 再生=frontend-b 配置页契约就位。
  ③ 出图去硬编码连接 `c24e565`：`_resolve_image_connection`——真实 provider 连接优先取默认 model_config（is_default+enabled、
     A1 真 key 从 api_key_env 环境变量取），无配/连接空/env key 未设 → 回落 .env GPT_IMAGE_*（**零回归**）。启动快照口径同 0042（切默认+重启生效）。
  测试：test_model_config CRUD 6 + 连接解析 3 + Out 无真 key；REAL_GPT_IMAGE=false 不走真 provider=零成本。ruff+mypy 绿、pytest 140 绿+1 已知红。
  **口径**：单模型槽+默认连接驱动 MVP（交付备用渠道切换核心价值）；**per-request 任意模型选择（请求 model 字段+string-keyed registry）列 P2 后续、本波不做**。
  待 coordinator 验收 + 迁移轮部署（qa 先行）；frontend-b 配置页 UI 随 openapi。owner→coordinator（部署编排）。
