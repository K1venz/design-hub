# 动态模型配置、Wan 2.7 接入与用户模型选择设计

- 日期：2026-07-30
- 状态：已完成口头设计确认，待书面审阅
- 范围：`image-code`、`image-web`
- 不在本期：钱包、用户侧计费、自动模型降级、任意 JSON 请求模板

## 1. 背景与目标

当前模型配置页混有 `seedream-5`、`lingdong-2`、`wanxiang-2.7-pro` 等 Mock
记录。新增记录仅能写入数据库，运行时仍由启动时的静态 `ModelName` 枚举和 Provider
Registry 决定，且 Chat 模型仍完全读取 `.env`。因此现状不能满足“管理员配置并测试后，
无需重启即可真实使用”。

本期目标：

1. 将生图模型与 Chat 模型明确分开。
2. 删除 Mock 模型记录，只保留真实模型。
3. 接入 `wan2.7-image-pro`，与 `gpt-image-2` 同时供用户选择。
4. 商品套图、爆款复刻、二次编辑、换背景、Chat 出图共用一个生图模型选择器。
5. 管理员新增或修改模型后必须进行真实能力测试；测试通过的精确配置才可启用。
6. 模型配置保存后对下一次调用立即生效，不重启 API 或 Worker。
7. API Key 加密保存，永不经读取接口、日志或审计记录回显。
8. 用户侧暂不展示单价、余额、预计成本；管理员统计继续保留。
9. 不做自动兜底或模型降级。用户选择哪个模型，就只调用哪个模型。

## 2. 已确认的产品边界

### 2.1 真实模型

生图模型：

- `gpt-image-2`，展示名“GPT Image 2.0”，初始默认。
- `wan2.7-image-pro`，展示名“Wan 2.7 Image Pro”，真实测试后启用。

Chat 模型：

- 当前豆包模型，作为独立 `chat` 类型模型和初始默认。

删除以下 Mock：

- `seedream-5`
- `lingdong-2`
- `wanxiang-2.7-pro`

`gpt-image-2-4k` 不再作为第三个用户可见模型。4K 是 GPT Image 的内部渲染档位。

### 2.2 Provider 边界

本期只允许选择代码已经支持的 Provider 协议：

- `openai_compat_image`
- `dashscope_wan_image`
- `openai_compat_chat`

不提供自由 JSON 模板。协议、字段或响应结构不同的模型必须先开发 Provider 适配器，
通过契约测试后才加入管理员下拉选项。

Wan 2.7 使用 DashScope 原生多模态接口，不使用 CSV 中的 OpenAI Compatible 地址：

- 异步提交：`POST {base_url}/services/aigc/image-generation/generation`
- 任务查询：`GET {base_url}/tasks/{task_id}`
- Base URL 来自 CSV 的 DashScope `/api/v1` 地址。

官方参考：

- <https://help.aliyun.com/en/model-studio/wan-image-generation-and-editing-api-reference>
- <https://help.aliyun.com/zh/model-studio/wan2-7-image-pro>

## 3. 数据模型

### 3.1 `model_config`

保留 `name` 作为稳定主键，重构为真实运行配置：

| 字段 | 类型/语义 |
|---|---|
| `name` | 稳定平台标识，如 `gpt-image-2` |
| `display_name` | 用户和管理员看到的名称 |
| `model_type` | `image` / `chat` |
| `provider_type` | 已支持的 Provider 协议 |
| `base_url` | Provider Base URL |
| `model` | 上游真实模型 ID |
| `credentials_ciphertext` | Provider 分字段 RSA 密文 JSON；永不回显 |
| `unit_cost` | 内部核算单价；仅管理员可见 |
| `enabled` | 是否允许新调用 |
| `revision` | 每次运行配置变更递增 |
| `verified_at` | 最近真实能力测试成功时间 |
| `verified_fingerprint` | 被测试配置的确定性指纹 |
| `extra` | 经过 Provider 白名单验证的非密钥参数 |

删除旧的 `api_key_env` 运行语义。正式运行时不再从 `.env` 回落。

连接指纹覆盖：

- `model_type`
- `provider_type`
- `base_url`
- 上游 `model`
- Provider 运行参数
- 解密后密钥的单向摘要

展示名和内部单价变化不影响连接指纹；其余运行字段变化会立即使验证状态失效。

### 3.2 Provider 分字段凭据

浏览器复用现有 RSA-OAEP-SHA256 公钥加密能力。每个敏感字段独立加密，避免把较长的
Provider 凭据 JSON 一次性塞进 RSA 明文长度上限。

示例字段：

- OpenAI Image：`standard_api_keys`、`four_k_api_key`
- DashScope Wan：`api_key`
- OpenAI Chat：`api_key`

读取接口只返回：

- `has_credentials`
- 各必要凭据是否已经配置

不得返回密文、密钥尾号或密钥摘要。审计日志只记录 `credentials_changed=true`。

生产必须使用持久的 `AUTH_RSA_PRIVATE_KEY_PEM`。私钥轮换需要先重新加密模型凭据，
不得在缺失或无法解密时回落到 `.env`。

### 3.3 默认模型

新增 `model_default`：

| 字段 | 语义 |
|---|---|
| `model_type` | 主键：`image` / `chat` |
| `model_name` | 指向同类型 `model_config` |

`model_config` 增加 `(model_type, name)` 唯一约束，`model_default` 使用
`(model_type, model_name)` 复合外键确保默认项类型正确。该表只决定：

- 用户第一次进入时选择哪个生图模型。
- 系统使用哪个 Chat 模型。

它不承担失败路由，也不允许自动降级。

## 4. 领域与任务模型

### 4.1 移除静态生图枚举约束

`GenerationItemSpec.model`、Pending Chat Action、Worker 路由等从 `ModelName` 枚举改为
经过模型配置服务验证的稳定字符串标识。删除 Mock 枚举值。

`RenderTier` 继续独立存在：

- `standard`
- `4k`

Chat 的 4K 意图只改变 `render_tier`，不再把模型改写成 `gpt-image-2-4k`。

### 4.2 用户选择固化

以下请求新增必填 `image_model`：

- `ListingGenerateRequest`
- `CloneRequest`
- `EditRequest`
- `BackgroundReplaceRequest`
- `ChatMessageRequest`

提交时：

1. 查询模型配置。
2. 验证 `model_type=image`、`enabled=true`、已验证且验证指纹仍匹配。
3. 使用模型内部单价生成 `reserved_cost`。
4. 把 `image_model` 写入每个 `generation_item.model`。
5. 把模型加入幂等请求指纹，避免相同 Idempotency-Key 在不同模型间误复用。

Worker 严格使用任务中的模型 ID。模型不可用时明确失败，不选择其他模型。

## 5. 动态 Provider 解析

### 5.1 Provider 工厂

新增统一 `ProviderFactory`：

- 输入经过验证的 `ModelConfigRecord`、Recorder、ImageStore。
- 按 `provider_type` 创建对应 Provider。
- 未知 Provider 立即失败。
- Provider 特定参数由各自 schema 校验，不接受任意透传 JSON。

现有 `OpenAICompatImageProvider` 和 `OpenAICompatTextProvider` 适配到该工厂，不复制请求逻辑。

### 5.2 Live Resolver

API/Worker 每次新调用都读取目标模型当前配置与 `revision`：

- 缓存命中条件为 `(model_name, revision, render_tier)` 完全一致。
- 版本变化时立即重建 Provider。
- 数据库读取失败时不使用旧配置发起新调用。
- 已经开始的上游请求使用开始时取得的 Provider，不中途切换。

不引入 Redis 配置事件。模型调用耗时远大于一次数据库查询，数据库保持唯一事实源。

### 5.3 Worker 重构

现有 Worker 启动时静态创建 Executor，不能支持新增模型热生效。重构为异步
`ProviderExecutorResolver`：

1. Worker 领取任务。
2. 按任务模型和渲染档位解析 Executor。
3. 获取该 Provider 的 `reference_mode`。
4. 再物化参考图。
5. 提交或恢复上游任务。

不为旧 Registry 增加兼容适配层；旧代码直接迁移到新解析结构。

## 6. DashScope Wan Provider

新增 `DashScopeWanImageProvider`，实现现有 `RecoverableTaskProvider`。

### 6.1 请求

- `reference_mode="bytes"`。
- 将参考图编码为 `data:{mime};base64,...`。
- `messages[0].content` 按顺序放参考图，最后放文本提示词。
- 每个 `generation_item` 固定 `n=1`。
- `watermark=false`。
- 尺寸使用当前比例映射得到的精确 `width*height`。
- 当前前端最多 3 张参考图，低于 Wan 官方最多 9 张限制。

### 6.2 异步生命周期

1. 提交时携带 `X-DashScope-Async: enable`。
2. 校验并返回 `task_id`。
3. Worker 立即将 `task_id` 写入现有 `provider_task_id`。
4. 恢复时查询 `/tasks/{task_id}`。
5. `PENDING/RUNNING` 继续等待。
6. `SUCCEEDED` 解析所有 `choices[].message.content[].image`。
7. 下载 24 小时有效的结果 URL，并立即存入现有 TOS/本地 ImageStore。
8. `FAILED/CANCELED/UNKNOWN` 映射为明确失败。

记录：

- Provider：`dashscope_wan_image`
- 上游模型
- 提交尝试次数
- 官方 `request_id`
- `image_count`
- 官方返回的 Token 字段（仅统计，不参与图片计费）
- 内部平台成本

### 6.3 能力校验

- 文生图：最高 4K。
- 带图编辑、复刻、换背景：最高 2K。
- 输入图尺寸、格式、文件大小在调用前校验。
- 业务参数错误、401/403 不重试。
- 429、超时、5xx 按现有 I/O 重试预算处理。
- 不自动切换 GPT Image。

### 6.4 GPT 4K

用户仍选择 `gpt-image-2`。当 `render_tier=4k` 时，Provider Factory 使用同一模型配置中的
4K 模型 ID 与独立密钥；UI 不出现第三个模型。

## 7. 管理员配置与测试

### 7.1 弹窗结构

字段：

- 模型类型
- Provider
- 稳定模型标识
- 展示名
- Base URL
- 上游模型 ID
- Provider 特定参数
- Provider 特定密钥
- 内部单价

Provider 和模型类型使用下拉选项，不再自由输入。

弹窗固定说明：

> 当前仅支持系统已经实现的 Provider 协议。OpenAI 兼容生图必须支持图片生成与编辑；
> OpenAI 兼容 Chat 必须支持流式响应和 Tool Calling。DashScope Wan 使用阿里云原生图片协议，
> 不属于 OpenAI Images API。保存前必须进行真实能力测试，测试会产生少量 API 调用。

### 7.2 测试 API

`POST /admin/models/test` 接收完整草稿配置和 RSA 密文：

- Image：真实测试一次生成和一次编辑。
- Chat：真实测试流式回复和一次必选 Tool Calling。
- 测试 ImageStore 使用进程内存，不写用户图库、数据库或对象存储。
- 返回分能力结果、耗时、可安全展示的错误、测试凭证和过期时间。

测试凭证：

- 对完整连接指纹、过期时间和用途前缀进行 HMAC 签名。
- 有效期 10 分钟。
- 保存时重新解密密钥并计算指纹。
- 指纹不一致、过期或签名错误时拒绝保存启用。

### 7.3 保存规则

- 新连接必须携带有效测试凭证。
- 连接字段变化必须重新测试。
- 展示名或内部单价变化无需测试。
- 未验证模型不能启用。
- 修改连接成功后 `revision += 1`。
- 所有保存、启停、默认切换和删除继续写管理员审计日志。
- 删除有非终态任务引用的模型时拒绝操作。

## 8. 用户模型目录与统一选择器

新增 `GET /models/image`：

- 只返回已启用且验证指纹有效的生图模型。
- 返回 `name`、`display_name`、`is_default`。
- 不返回单价、Provider、Base URL、上游模型或任何凭据信息。

`ImageModelSelector` 用于：

- 商品套图
- 爆款复刻
- 二次编辑
- 换背景
- Chat 出图

最近选择按 `user_id` 保存到浏览器持久状态。首次进入采用 API 返回的默认模型。

Chat 的选择器只决定出图工具使用的生图模型，不改变负责对话、知识库和反推提示词的 Chat 模型。
LLM 工具参数中不包含模型字段，不能覆盖用户选择。

## 9. 前端鲁棒性硬性要求

### 9.1 模型目录

- 加载中：显示固定高度 Skeleton，防布局跳动；出图按钮禁用。
- 请求失败：显示就地错误和“重新加载”，保留用户已填表单、上传图和 Chat 草稿。
- 空列表：显示“当前没有可用生图模型”，所有出图入口禁用，不硬编码 GPT。
- 持久选择已经停用或删除：清除该用户的失效选择，要求重新选择，不静默切换。
- 默认模型数据异常：选择器进入必选状态，不猜测默认。

### 9.2 提交竞态

- 模型目录未完成前，任何入口不得提交。
- 提交按钮在请求期间禁用，避免双击；现有 Idempotency-Key 继续生效。
- 模型在目录加载后被管理员停用：后端拒绝，前端刷新目录、保留全部表单内容并提示重新选择。
- 模型必须进入请求幂等指纹。
- 管理员保存后先等待服务端成功，再刷新管理列表和用户模型目录，不做乐观启用。

### 9.3 Chat

- Hero 自动发送必须等待模型目录完成。
- 目录失败或为空时，把 Hero 文案保留为草稿，不发送缺少模型的请求。
- Streaming 或等待出图确认时锁定本轮模型选择。
- 确认卡显示本轮固化的模型，即使用户之后切换全局选择也不改变 Pending Action。
- 中断 SSE 后正确释放锁定状态，不能残留“生成中”。

### 9.4 管理员测试弹窗

- 测试中禁用重复测试、保存、Provider 切换和关闭破坏性操作。
- 长时间测试显示阶段与耗时，不显示假进度。
- 网络失败保留全部输入，允许重试。
- 任一影响连接指纹的字段变化立即清除成功状态和测试凭证。
- API Key 编辑框永不回填；留空表示保留现有密钥，输入新值表示替换。
- 创建弹窗关闭后清理敏感表单状态。
- 服务端错误只显示已清洗的错误类别，不展示上游响应体或请求头。

### 9.5 历史与下线模型

- 历史任务保存模型稳定标识。
- 当前目录仍有该模型时显示最新展示名。
- 模型已经删除时回退显示任务中保存的稳定标识，不显示空白或报错。

### 9.6 响应式与可访问性

- 桌面与移动端选择器不溢出。
- 支持键盘选择、正确 Label 和 `aria` 状态。
- Loading/Error/Empty 状态保持可读，不只依赖颜色。

## 10. 暂时隐藏用户价格

移除所有用户侧金额：

- 首页工具卡
- 单图/套图配置与 CTA
- 爆款复刻 CTA
- 二次编辑 CTA
- 换背景 CTA
- Chat 确认卡
- 历史列表
- 历史详情和迭代链累计

管理员模型配置、调用统计和成本核算继续显示内部单价。

Chat 的 `cost_confirm` 改为 `generation_confirm`：

- 对用户只返回模型展示名、张数、确认 token。
- Pending Action 内部仍保留预留成本，供现有平台成本保护。
- 文案改为“确认后开始调用模型”，不出现计费、扣费、余额。

内部额度触顶只向用户显示“当前出图额度已达到上限”，不显示金额。钱包与用户计费另开设计，
不在本期预埋钱包表或兼容层。

## 11. Chat 知识库同步

更新并复核 `design_hub/config/chat_knowledge.md`：

- 增加 GPT Image 2.0 与 Wan 2.7 Image Pro。
- 说明所有出图入口均可使用统一模型选择器。
- 删除“显示预计费用”“查询具体单价与余额”等不真实内容。
- 用户问价格时回答：“当前暂未开放钱包和公开计费，具体规则上线后以页面展示为准。”
- 将价格查询工具改为模型能力查询工具。
- 检查现有入口、比例、4K、编辑、换背景、反推提示词和暂不支持列表是否仍真实。

## 12. 迁移与安全初始化

Alembic Migration 只处理 schema 和非敏感数据：

1. 增加模型配置字段与默认模型表。
2. 删除三个 Mock 行。
3. 创建 GPT、Wan、豆包的非敏感配置骨架。
4. 不在 Migration 中读取或写入密钥。

新增一次性安全初始化命令：

- 从现有 `GPT_IMAGE_*`、`TEXT_LLM_*` 读取 GPT、4K 和豆包凭据。
- 从显式传入的 `--wan-csv` 路径读取 Wan Base URL 与 API Key。
- 使用服务器 RSA 公钥逐字段加密并写入数据库。
- 不输出密钥、密文或 CSV 内容。
- 调用同一测试服务完成真实能力测试，成功后启用。
- 完成后正式运行链路只读数据库。

用户提供的 CSV 仅作为通过 `--wan-csv` 显式传入的一次性本地输入，不得复制到仓库、
容器镜像、测试 fixture 或日志。

## 13. 测试与验收

后端：

- Model Config schema、Repo、加密、不回显、审计脱敏。
- 测试凭证签名、过期、篡改、字段变化失效。
- 未验证/停用/类型错误模型拒绝提交。
- 五个入口的 `image_model` 校验和幂等指纹。
- 动态 Provider revision 热生效。
- Wan 生成、编辑、异步提交、恢复、轮询、下载、错误和重试。
- GPT Image、4K、豆包 Chat 回归。
- Worker 重启后从 `provider_task_id` 恢复 Wan。
- 管理后台调用次数与模型统计。
- SQLite 与生产 MySQL Migration。

前端：

- 统一选择器五入口一致性。
- 按用户持久化。
- Loading/Error/Empty/失效选择。
- 模型停用竞态。
- Chat Hero 自动发送等待目录。
- Pending 模型固化。
- Admin 测试状态机和敏感字段清理。
- 所有用户价格文案移除。
- 历史下线模型回显。
- 类型检查、Lint、单测、生产构建。

真实冒烟：

1. 使用提供的 Wan Key 测试一张生成图。
2. 使用生成结果测试一次编辑。
3. 验证异步 `task_id` 持久化和结果下载。
4. 验证 GPT Image 原有生成、编辑和 4K 不回归。
5. 本地启动 API、Worker、Web，通过五个入口检查模型选择。

预计 Wan 真实冒烟产生两张计费图片调用。

## 14. 非目标

- 钱包、充值、用户侧扣费和套餐。
- 自动模型降级、失败切换、优先级路由。
- 任意 JSON 模板或可编程响应映射。
- 用户自定义 API Key。
- 用户针对不同入口保存不同模型偏好。
- Redis 模型配置广播。
