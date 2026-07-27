# 1K / 4K 独立 Key 池与 Chat 工具收口 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 普通图片只使用两把 1K Key，4K 图片只使用独立 4K Key，并让 Chat 的风格与 4K 要求不再进入旧 modifiers 校验链。

**Architecture:** Settings 新增独立 4K SecretStr；Composition Root 为两个模型分别创建 `ApiKeyPool`，禁止共享或跨池降级。Chat 三个写工具使用不含 modifiers 的专属 DTO，风格只进入 prompt，模型由后端确定性路由。

**Tech Stack:** Python 3.12、Pydantic Settings、FastAPI application services、pytest、Ruff、Mypy、OpenAI-compatible Images API。

## Global Constraints

- 不新增数据库字段、迁移或模型配置数据。
- 1K 固定模型 `gpt-image-2`；4K 固定模型 `gpt-image-2-4k`。
- 1K Key 数量必须为 2；4K Key 数量必须为 1；不得跨池重试或降级。
- Key 值不得进入源码、测试、文档、提交、日志或命令输出。
- 不进行真实付费生图测试。

---

### Task 1: Provider 独立 Key 池

**Files:**
- Modify: `image-code/src/design_hub/config/settings.py`
- Modify: `image-code/src/design_hub/composition.py`
- Test: `image-code/tests/test_image_model_composition.py`

**Interfaces:**
- Consumes: `Settings.gpt_image_api_key` 作为 1K 逗号分隔池
- Produces: `Settings.gpt_image_4k_api_key: SecretStr` 与两个独立 `ApiKeyPool`

- [ ] **Step 1: 写失败测试**

在 `_settings()` 中提供两个 1K 测试 Key 和一个独立 4K 测试 Key，断言：

```python
assert standard._key_pool is not four_k._key_pool
assert standard._key_pool.size == 2
assert four_k._key_pool.size == 1
```

并覆盖缺少 4K Key、4K 配置含两把 Key时 fail-fast。

- [ ] **Step 2: 运行 RED**

```bash
cd image-code
uv run pytest -q tests/test_image_model_composition.py
```

Expected: FAIL，当前两个 Provider 仍共享同一池且 Settings 没有独立 4K Key。

- [ ] **Step 3: 实现独立配置与组装**

新增：

```python
gpt_image_4k_api_key: SecretStr = SecretStr("")
```

`build_gpt_image_providers()` 分别构造 `standard_key_pool` 与 `four_k_key_pool`；
4K Key 拆分后必须恰好一把，否则 `ValueError`。

- [ ] **Step 4: 运行 GREEN**

```bash
cd image-code
uv run pytest -q tests/test_image_model_composition.py tests/test_provider_resilience.py
uv run ruff check src tests
uv run mypy src
```

- [ ] **Step 5: 提交**

```bash
git add image-code/src/design_hub/config/settings.py image-code/src/design_hub/composition.py image-code/tests/test_image_model_composition.py
git commit -m "refactor(image): 拆分 1K 与 4K Key 池"
```

---

### Task 2: Chat 写工具移除 modifiers

**Files:**
- Modify: `image-code/src/design_hub/application/chat/tool_requests.py`
- Modify: `image-code/src/design_hub/application/chat/orchestrator.py`
- Modify: `image-code/src/design_hub/application/chat/system_prompt.py`
- Test: `image-code/tests/test_chat.py`
- Test: `image-code/tests/test_chat_harness.py`

**Interfaces:**
- Consumes: generate、clone、edit 的 LLM tool arguments
- Produces: `ChatGenerateRequest`、`ChatCloneRequest`、`ChatEditRequest`，均不含 modifiers；转换后的 listing DTO 使用空 modifiers

- [ ] **Step 1: 写失败测试**

断言三个 Chat 写工具 schema 都没有 `modifiers`；用“我要生成 4K 图，国风风格的”和
不含 modifiers 的 generate tool call 验证进入 4K `cost_confirm`，价格为 `0.18`。

- [ ] **Step 2: 运行 RED**

```bash
cd image-code
uv run pytest -q tests/test_chat.py tests/test_chat_harness.py -k "modifier or national_style_4k"
```

Expected: FAIL，当前 schema 仍暴露 modifiers。

- [ ] **Step 3: 实现 Chat 专属 DTO**

移除 generate/clone 的 modifiers，新增不含 modifiers 的 `ChatEditRequest`；三个
`to_listing()` 显式传 `modifiers={}`。`_tool_specs()` 与 `_parse_req()` 使用专属 DTO。
System prompt 增加“不得生成 modifiers 字段；风格只写入 prompt”。

- [ ] **Step 4: 运行 GREEN**

```bash
cd image-code
uv run pytest -q tests/test_chat.py tests/test_chat_harness.py tests/test_chat_rendering_intent.py
uv run ruff check src tests
uv run mypy src
```

- [ ] **Step 5: 提交**

```bash
git add image-code/src/design_hub/application/chat/tool_requests.py image-code/src/design_hub/application/chat/orchestrator.py image-code/src/design_hub/application/chat/system_prompt.py image-code/tests/test_chat.py image-code/tests/test_chat_harness.py
git commit -m "refactor(chat): 从写工具移除旧 modifiers"
```

---

### Task 3: 部署配置、安全验收与发布

**Files:**
- Modify: `image-ops/deploy/.env.example`
- Modify: `image-ops/deploy/scripts/deploy.sh`
- Secure local-only update: `image-code/.env`
- Secure production-only update: `/opt/docker/design-hub/.env`

**Interfaces:**
- Consumes: `GPT_IMAGE_API_KEY`（2 把 1K）、`GPT_IMAGE_4K_API_KEY`（1 把 4K）
- Produces: 本地与生产独立凭据配置

- [ ] **Step 1: 更新无密钥模板**

在 `.env.example` 与新安装 `.env` 模板中增加空的 `GPT_IMAGE_4K_API_KEY=`，不写任何值。

- [ ] **Step 2: 安全重写本地 `.env`**

不打印值，只验证：

```text
GPT_IMAGE_API_KEY count=2
GPT_IMAGE_4K_API_KEY count=1
permission=600
```

- [ ] **Step 3: 运行完整 CI 与安全扫描**

```bash
cd image-code
uv run pytest -q
uv run ruff check src tests
uv run mypy src
uv run alembic heads
cd ../image-web
npm test
npm run lint
npm run typecheck
npm run build
```

确认 Git tracked diff 不含 Key 模式。

- [ ] **Step 4: 提交部署模板**

```bash
git add image-ops/deploy/.env.example image-ops/deploy/scripts/deploy.sh
git commit -m "chore(deploy): 增加独立 4K Key 配置"
```

- [ ] **Step 5: 发布生产并验证**

按现有 SOP 创建回滚镜像、备份生产 `.env` 和 MySQL、推送 dev/main、运行 `push.sh` 与
`deploy.sh`。只读验证 API healthy、1K/4K Key 数量 2+1、Alembic head 不变、无新增
4K model_config 行、近期错误日志为 0。
