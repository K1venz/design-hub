# 独立视觉模型与反推提示词设计

## 目标

将反推提示词从默认 Chat 模型中拆出，建立独立的视觉模型配置、默认模型和真实能力验证链路。生产环境使用豆包 Seed 2.0 Lite 视觉理解能力，并复用现有豆包连接的 Base URL 与加密 API Key。

## 问题现状

- `ReversePromptService` 调用 `TextLLMResolver.resolve_default()`。
- `LiveTextLLMResolver.resolve_default()` 固定读取 `ModelType.CHAT` 的默认模型。
- 用户在 Chat 工作台切换模型不会改变反推提示词的模型选择。
- 当前默认 Chat 模型 DeepSeek V4 Flash 不支持图片输入，因此包含 `image_url` 的请求被上游以 HTTP 400 拒绝。
- 后台模型管理只有 `image` 和 `chat` 两种类型，无法独立配置视觉理解模型。

## 已确认方案

### 独立模型类型

新增 `ModelType.VISION = "vision"`。`model_default` 继续按 `model_type` 保存默认项，因此视觉模型天然拥有独立默认值，不与 Chat 或图片生成模型竞争。

OpenAI 兼容 Chat Completions 是一种连接协议，不再被限定为只服务 `chat` 类型。`openai_compat_chat` Provider 同时允许 `chat` 与 `vision` 类型，但不同类型必须分别建模、验证和设为默认。

### 解析接口

文本/多模态补全解析器改为显式接收期望模型类型：

```python
async def resolve(
    self,
    model_id: str,
    model_type: ModelType,
) -> TextLLMPort: ...

async def resolve_default(
    self,
    model_type: ModelType,
) -> TextLLMPort: ...
```

Chat 编排器始终传入 `ModelType.CHAT`；反推提示词始终传入 `ModelType.VISION`。模型类型不匹配时直接报 `ModelUnavailableError`，不回退到 Chat 默认模型。

### 豆包模型

生产视觉模型配置：

- 稳定 ID：`doubao-vision`
- 展示名称：`豆包 Seed 2.0 Lite 视觉`
- 类型：`vision`
- Provider：`openai_compat_chat`
- 上游模型：`doubao-seed-2-0-lite-260428`
- Base URL：复制现有 `doubao-chat`
- API Key：复制现有 `doubao-chat` 的密文，不在迁移、日志或源码中出现明文
- 默认项：视觉类型默认模型

旧版豆包 1.5 Vision 已退役，不作为候选。模型必须通过生产环境真实能力测试后才能启用。

### 视觉能力验证

后台对 `vision` 类型执行与实际反推提示词一致的验证：

1. 构造确定性的红色 PNG 测试图。
2. 通过 `ChatMessage.images` 发送图片。
3. 强制调用结构化工具，返回图片主色。
4. 只有工具名称、JSON 参数和主色均符合预期才签发验证证明。

该测试同时覆盖图片输入、流式 Chat Completions、函数调用和结构化 JSON，避免只验证文本连通性后错误启用视觉模型。

### 后台界面

- 模型类型筛选增加“视觉模型”。
- 模型配置弹窗增加“视觉模型”选项。
- `openai_compat_chat` 在 Chat 和视觉模型中均可选。
- 类型列显示“视觉”，默认标签继续显示“类型默认”。
- 验证说明明确视觉模型会检查“图片理解 + 结构化工具调用”。

视觉模型仍复用现有模型管理页面，不增加独立页面，保持当前后台 UI 体系一致。

## 数据迁移与生产配置

数据库迁移通过 `INSERT ... SELECT` 从 `doubao-chat` 复制连接字段和加密凭据，创建未启用、未验证的 `doubao-vision`。部署后通过后台能力测试或等价的应用服务调用完成真实验证，再启用并设为 `vision` 默认模型。

如果现有豆包 API Key 无权访问 `doubao-seed-2-0-lite-260428`，测试必须失败且模型保持停用；系统不得回退到文本模型。

## 错误处理

- 未配置、未启用、未验证或指纹不一致的视觉模型统一抛出 `ModelUnavailableError`。
- 上游 HTTP 或响应协议错误继续由 `TextLLMError` 表达，并记录到模型调用日志。
- 不增加非网络重试、静默降级或 Chat 模型回退。

## 验收标准

- Chat 默认模型和视觉默认模型可独立配置。
- 切换 Chat 模型不影响反推提示词使用的视觉模型。
- 后台可创建、编辑、验证、启停和设为默认视觉模型。
- 视觉能力验证必须实际读取图片并完成强制工具调用。
- 生产 `doubao-vision` 通过真实验证后启用并成为视觉默认模型。
- 使用一张真实图片调用反推提示词成功返回完整中英文结构化结果。
- API Key 不出现在源码、迁移、终端输出或用户可见日志中。
