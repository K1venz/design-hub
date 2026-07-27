# 生图结果存储归一化 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 无论 GPT Image API 返回 `b64_json` 还是外部 `url`，都先转存平台 ImageStore，并让数据库只持久化明确的内部 `image_key`。

**Architecture:** `ImageStore.save()` 返回同时包含稳定 Key 和即时访问 URL 的 `StoredImage`，`GeneratedImage` 将 `image_key` 作为一等字段，任务持久化不再从 URL 反向猜 Key。OpenAI-compatible provider 优先消费 `b64_json`；只有缺少 Base64 时才无鉴权下载外部 URL，校验后转存平台存储。

**Tech Stack:** Python 3.12、FastAPI application services、httpx、TOS/local ImageStore、pytest、Ruff、Mypy。

## Global Constraints

- MySQL `listing_image.image_key VARCHAR(128) NOT NULL` 保持不变，不新增数据库迁移。
- 不增加兼容层；所有现有 Provider、ImageStore 实现和测试替身统一迁移到新契约。
- 上游 URL、签名参数和 Base64 内容不得写入数据库。
- 外部图片下载不得携带生图 API Bearer Key。
- 网络瞬时错误可以重试；非法 URL、非图片响应、空响应和超限响应必须 fail-fast。
- 不进行真实付费生图测试。

---

### Task 1: 内部图片存储契约

**Files:**
- Modify: `src/design_hub/ports/image_store.py`
- Modify: `src/design_hub/domain/models.py`
- Modify: `src/design_hub/infrastructure/storage/local.py`
- Modify: `src/design_hub/infrastructure/storage/tos.py`
- Modify: `src/design_hub/infrastructure/providers/mock.py`
- Modify: `src/design_hub/infrastructure/providers/apinebula_async.py`
- Modify: `src/design_hub/application/listing/commands.py`
- Modify: `tests/test_async_provider.py`
- Modify: `tests/test_listing_history_persistence.py`
- Modify: `tests/test_listing_validation.py`
- Modify: `tests/test_provider_resilience.py`

**Interfaces:**
- Produces: `StoredImage(key: str, url: str)`
- Produces: `ImageStore.save(data: bytes, *, suffix: str = ".png") -> StoredImage`
- Produces: `GeneratedImage(image_key: str, url: str, seed: int, latency_ms: int, cost: Decimal, image_type: str | None = None)`
- Consumes: `ListingCommand._persist_and_complete()` 直接读取 `GeneratedImage.image_key`

- [ ] **Step 1: 写失败测试**

在 `tests/test_listing_history_persistence.py` 构造 URL 末段超过 128 字符、但显式
`image_key="owned.png"` 的 `GeneratedImage`，断言任务完成且历史只保存：

```python
assert persisted.image_key == "owned.png"
```

该测试捕获“持久化重新从展示 URL 猜 Key”的生产缺陷。

- [ ] **Step 2: 运行 RED**

```bash
uv run pytest -q tests/test_listing_history_persistence.py -k explicit_image_key
```

Expected: FAIL，当前 `GeneratedImage` 不接受 `image_key`，任务仍从 URL 提取 Key。

- [ ] **Step 3: 实现明确存储契约**

新增：

```python
@dataclass(frozen=True)
class StoredImage:
    key: str
    url: str
```

让本地/TOS `save()` 返回 `StoredImage`；所有 Provider 与测试替身构造
`GeneratedImage` 时显式传 `image_key`。`ListingCommand` 删除
`image_key_from_url()` 依赖，直接持久化 `im.image_key`。

- [ ] **Step 4: 运行 GREEN**

```bash
uv run pytest -q tests/test_listing_history_persistence.py tests/test_async_provider.py tests/test_listing_validation.py tests/test_provider_resilience.py
uv run ruff check src tests
uv run mypy src
```

- [ ] **Step 5: 提交**

```bash
git add src tests
git commit -m "refactor(image): 显式传递生图存储 Key"
```

---

### Task 2: OpenAI-compatible 返回结果转存

**Files:**
- Modify: `src/design_hub/infrastructure/providers/openai_compat.py`
- Modify: `src/design_hub/composition.py`
- Modify: `tests/test_provider_contract.py`
- Modify: `tests/test_provider_resilience.py`
- Modify: `tests/test_image_model_composition.py`

**Interfaces:**
- Consumes: 上游 `data[].b64_json` 或 `data[].url`
- Produces: 只指向平台 ImageStore 的 `GeneratedImage.image_key` 与 `GeneratedImage.url`
- Produces: 外部 URL 下载请求不带 `Authorization`

- [ ] **Step 1: 写失败测试**

在 `tests/test_provider_contract.py` 增加两个行为用例：

```python
assert image.image_key == "stored.png"
assert image.url == "https://owned.example/stored.png?signature=local"
```

第一例让上游同时返回 `b64_json` 与超长 `url`，断言优先解码 Base64 并只保存一次；
第二例只返回超长 HTTPS URL，模拟下载 `image/png` 后断言转存成功，且下载请求没有
`Authorization`。

再增加非法 scheme、非图片 Content-Type、空响应和超过 64 MiB 时抛
`ProviderError` 的边界用例。

- [ ] **Step 2: 运行 RED**

```bash
uv run pytest -q tests/test_provider_contract.py -k "stored or external_image"
```

Expected: FAIL，当前实现优先接受外部 URL，并把它直接交给任务层。

- [ ] **Step 3: 实现 URL 下载与转存**

让 `OpenAICompatImageProvider` 强制要求 `ImageStore`。解析顺序固定为：

```text
b64_json -> 严格 Base64 解码 -> ImageStore.save()
url only -> 校验 http/https -> 无鉴权 GET -> 校验 image/*、非空、<=64 MiB
         -> ImageStore.save()
```

URL 下载的 429/5xx/超时/传输错误使用现有退避参数重试，但不得重新调用生图接口；
所有下载必须受该次生图操作的总墙钟约束。最终构造：

```python
GeneratedImage(image_key=stored.key, url=stored.url, ...)
```

- [ ] **Step 4: 运行 GREEN 与完整 CI**

```bash
uv run pytest -q tests/test_provider_contract.py tests/test_provider_resilience.py tests/test_image_model_composition.py
uv run pytest -q
uv run ruff check src tests
uv run mypy src
uv run alembic heads
```

Expected: 全部通过，Alembic 仍为单一既有 head，无新迁移。

- [ ] **Step 5: 提交**

```bash
git add src tests
git commit -m "fix(image): 转存上游 URL 生图结果"
```

---

### Task 3: 最终安全验收

**Files:**
- Verify only: `src/`
- Verify only: `tests/`
- Verify only: `migrations/`

**Interfaces:**
- Consumes: Task 1、Task 2 的提交结果
- Produces: 可交付的本地修复分支，不推送、不部署

- [ ] **Step 1: 检查差异和数据库边界**

```bash
git diff dev...HEAD --check
git diff dev...HEAD -- migrations
git status --short
```

Expected: whitespace 检查通过，`migrations/` 无变化，只包含本需求计划、源码和自动化测试。

- [ ] **Step 2: 核对关键回归**

确认以下行为均由自动化测试覆盖：

```text
长上游 URL 不进入 image_key
b64_json 优先于 url
URL-only 结果转存平台存储
下载不泄露 Bearer Key
普通 1K 与 4K 共用同一归一化行为
历史预览与继续编辑仍使用内部 Key
```

- [ ] **Step 3: 报告交付状态**

报告分支、提交、测试数量、静态检查结果和未执行事项；未经用户明确要求，不推送远程、不部署环境。
