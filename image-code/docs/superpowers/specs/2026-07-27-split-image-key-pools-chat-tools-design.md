# 1K / 4K 独立 Key 池与 Chat 工具收口设计

## 目标

普通图片只使用两把 `gpt-image-2-1k` 分组 Key；4K 图片只使用一把 `image2-4k`
分组 Key。Chat 中的“4K、国风、复古”等自然语言要求不得进入旧工作台
`modifiers` 校验链，必须分别由后端模型路由和最终图片 prompt 承载。

## 上游契约

- 1K：同步 `POST /v1/images/generations`、`POST /v1/images/edits`，模型固定
  `gpt-image-2`。一次请求只返回一张，不支持 2K/4K。
- 4K：使用相同同步端点，模型固定 `gpt-image-2-4k`，尺寸固定
  `3840x2160`、`quality=high`，总墙钟 1800 秒。
- 两组请求使用相同中转站 base URL，但凭据权限组不同，禁止跨池重试、降级或兜底。

## 配置与 Provider 组装

- `GPT_IMAGE_API_KEY`：只保存两把 1K Key，逗号分隔。
- 新增 `GPT_IMAGE_4K_API_KEY`：只保存一把 4K Key。
- 普通 Provider 使用 `ApiKeyPool` 包装两把 1K Key，按现有规则轮换和重试。
- 4K Provider 使用独立 `ApiKeyPool`，池中只有 4K Key。
- `build_gpt_image_providers()` 必须 fail-fast：
  - 1K 池为空时拒绝启动真实图片 Provider；
  - 4K Key 为空或包含多把 Key 时拒绝启动；
  - 两个 Provider 不得共享 `ApiKeyPool` 实例。
- 不新增数据库字段、迁移或模型配置数据。

## Chat 工具契约

Chat 的 generate、clone、edit 都不再暴露 `modifiers`：

- 用户的“国风、写实、复古”等视觉要求保留在 `prompt`。
- 4K 由 `rendering_intent` 的确定性状态机选择运行时 Provider。
- Chat 专属 DTO 转换到 listing DTO 时显式使用空 `modifiers`。
- 结构化工作台仍可继续使用平台、地区和语言 modifiers，不受本改动影响。
- System prompt 明确禁止生成 `modifiers` 字段，避免文本 LLM 重复编码 4K 或风格。

## 密钥与发布

- Key 值只写 gitignored、权限为 `600` 的本地与生产 `.env`。
- 源码、测试、文档、提交、日志和最终报告均不得包含 Key 值。
- 发布时先备份生产 `.env`；只报告 1K Key 数量为 2、4K Key 数量为 1。
- 不执行真实付费生图测试；使用 HTTP Stub 分别验证两个 Provider 发出正确模型和 Key。

## 验收

- “我要生成 4K 图，国风风格的”进入 4K 费用确认，不出现
  “暂不支持的选项：4K”。
- 普通请求只使用 1K 池；4K 请求只使用 4K 池。
- Chat 三个写工具 schema 均不包含 `modifiers`。
- 后端完整测试、Ruff、Mypy、前端测试与生产构建通过。
- 生产 API healthy，Key 数量为 2+1，Alembic head 与数据库数据不变。
