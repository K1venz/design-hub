---
id: ISSUE-0057
title: 「配置大模型」页面——管理员全局配 model_config + 通用中转 provider + 用户选模型（档 A）
status: 待确认        # 用户拍档 A、dev 出技术设计+schema 提案；待 PM 立需求 + 用户签 DB schema 后方可开工
severity: P2          # 新特性（获客/灵活性 + 附带缓解 ISSUE-0056 单点故障）；非阻断、非资损
reporter: 开发        # 用户 2026-07-07 经 dev 窗口提需求（盘点占位符时衍生），dev 出技术设计并路由 PM 立需求
owner: PM             # 立需求：反转 ISSUE-0017「不做其他模型」范围 + 定 UX + 关账口径；DB schema 待用户签字
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
