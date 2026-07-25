# Global Image Quality Policy and Chat 4K Routing Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Status:** 已实现，待最终全量验收。

**Goal:** 为所有真实 GPT Image 请求统一注入全品类真实性与细节质量约束，并让 Chat 仅在用户本轮明确要求 4K 时按固定 16:9、¥0.18/张调用 `gpt-image-2-4k`；普通请求继续按原比例规则和 ¥0.05/张调用 `gpt-image-2`。

**Architecture:** 在 Provider 最终请求边界统一组合全局质量策略、业务提示词和负向提示词；普通与 4K 运行时 Provider 都调用同步 `/v1/images/generations` 或 `/v1/images/edits`，并共用一个无密钥泄露的轮换池。Chat 在 LLM 前注入 4K 的 16:9 比例事实，只在写工具被选择后执行确定性冲突检查，并将所选模型保存在费用确认快照中，确认后仅在运行时传递到 launcher、Provider 和费用流程。

**Tech Stack:** Python 3.12、FastAPI、Pydantic、SQLAlchemy 2、Alembic、httpx、pytest、Ruff、Mypy；React 19、TypeScript、Vite、Vitest、ESLint。

## Global Constraints

- 严格遵循已确认规格：`image-code/docs/superpowers/specs/2026-07-25-global-image-quality-4k-chat-design.md`。
- 不在源码、测试、文档、迁移、提交消息或命令输出中写入三把 API Key；只安全更新 gitignored 环境文件，并且只验证 Key 数量。
- 不把全局质量策略写回用户消息、`listing_job.prompt` 或其他历史字段。
- 普通模型继续支持现有五种比例；4K 只允许 `3840x2160`（16:9）、`quality=high`、`n=1`。
- 4K 失败不得降级到普通模型。确定性 4xx 立即失败；仅 429、5xx、传输错误可在 1800 秒总墙钟预算内换 Key 重试。
- 两个运行时模型只接受 `openai_compat_image` 连接协议；完整但不兼容的默认连接 fail-fast。
- 用户最终裁决已取代原持久化/迁移方案：模型只做运行时路由和费用确认快照传递，不写入 `listing_job` 或历史 API，不新增迁移；生产 MySQL schema 与 Alembic head `f3a4b5c6d7e8` 保持不变。
- 本需求不更新默认、开发或生产持久数据库及其数据；普通 ¥0.05、4K ¥0.18 是 registry 固定运行时价格，持久旧价格不得覆盖。启动 `seed_defaults` 不含 4K 行；缺失 4K 行不禁用能力，存在且 disabled 才禁用。可启动性冒烟允许使用一次性 `mktemp` SQLite 测试 fixture，验收后停止进程并删除临时数据库；这不属于持久数据库更新，也不改变项目 schema。
- 4K Chat 单次最多 3 张，超限必须在 tool call、费用确认、pending 和 job 前返回固定用户文案。
- Chat 长等待每 20 秒发送 SSE comment 心跳；启动 reaper 使用 45 分钟阈值；预扣后取消必须先退款并把 job 收口为失败，再重新抛出 `CancelledError`。
- 每个任务先写失败测试，再实现最小完整改动，再跑针对性测试并立即提交。
- 未再次获得用户明确授权，不执行真实付费生图。实现验收使用 Mock、HTTP Stub 和本地 Chat。

---

## Task 1: 建立统一的全局质量提示词边界

**Files:**

- Create: `image-code/src/design_hub/application/image_generation/__init__.py`
- Create: `image-code/src/design_hub/application/image_generation/prompt_policy.py`
- Modify: `image-code/src/design_hub/infrastructure/providers/_openai_common.py`
- Modify: `image-code/src/design_hub/infrastructure/providers/openai_compat.py`
- Modify: `image-code/src/design_hub/infrastructure/providers/apinebula_async.py`
- Create: `image-code/tests/test_image_quality_prompt.py`
- Modify: `image-code/tests/test_provider_contract.py`
- Modify: `image-code/tests/test_async_provider.py`

- [ ] **Step 1: 为提示词顺序、单次注入和持久化隔离写失败测试**

在 `test_image_quality_prompt.py` 覆盖：

```python
def test_compose_image_api_prompt_orders_policy_task_and_negative() -> None:
    prompt = compose_image_api_prompt("生成红色水杯", "不要水印")

    assert prompt.startswith("【全局真实性与细节质量约束】")
    assert prompt.index("【本次生图要求】") < prompt.index("生成红色水杯")
    assert prompt.index("生成红色水杯") < prompt.index("【需要避免】")
    assert prompt.endswith("不要水印")
    assert prompt.count("【全局真实性与细节质量约束】") == 1


def test_compose_image_api_prompt_omits_empty_negative_section() -> None:
    prompt = compose_image_api_prompt("生成扁平 Logo", "")

    assert "【需要避免】" not in prompt


def test_compose_image_api_prompt_rejects_empty_task_prompt() -> None:
    with pytest.raises(ValueError, match="task prompt"):
        compose_image_api_prompt("   ", "")
```

在普通与 4K 两个同步运行时 Provider 合约测试中分别抓取 generation/edit HTTP payload，
断言最终 `prompt` 含全局策略一次、业务 prompt 一次、negative 位于末尾；保留异步适配器
也验证同一 prompt policy，但它不参与 runtime composition。另在 listing 历史测试中断言
数据库保存的仍是原业务 prompt。

- [ ] **Step 2: 运行测试并确认失败原因是策略模块尚不存在**

Run:

```bash
cd image-code
uv run pytest tests/test_image_quality_prompt.py tests/test_provider_contract.py tests/test_async_provider.py -q
```

Expected: FAIL，导入 `prompt_policy` 失败或 Provider payload 尚未包含全局策略。

- [ ] **Step 3: 实现单一提示词组合函数**

在 `prompt_policy.py` 中逐字保存规格第 5 节代码块内的完整固定文本为
`GLOBAL_IMAGE_QUALITY_POLICY`，不得缩写、改写或复制第二份，并实现：

```python
def compose_image_api_prompt(task_prompt: str, negative_prompt: str) -> str:
    task = task_prompt.strip()
    if not task:
        raise ValueError("task prompt must not be empty")

    sections = [
        f"【全局真实性与细节质量约束】\n\n{GLOBAL_IMAGE_QUALITY_POLICY}",
        f"【本次生图要求】\n\n{task}",
    ]
    negative = negative_prompt.strip()
    if negative:
        sections.append(f"【需要避免】\n\n{negative}")
    return "\n\n".join(sections)
```

删除 `_openai_common.py` 中旧的负向提示拼接职责；两个同步运行时 Provider 以及保留的
异步适配器在构造网络 payload 时都只调用 `compose_image_api_prompt()`。不要在 listing
service 或 Chat orchestrator 中提前注入。

- [ ] **Step 4: 运行针对性测试和静态检查**

Run:

```bash
cd image-code
uv run pytest tests/test_image_quality_prompt.py tests/test_provider_contract.py tests/test_async_provider.py tests/test_listing_history_persistence.py -q
uv run ruff check src tests
uv run mypy src
```

Expected: PASS；捕获到的网络 prompt 只注入一次，持久化 prompt 不含全局标题。

- [ ] **Step 5: 提交全局质量策略单元**

```bash
git add image-code/src/design_hub/application/image_generation image-code/src/design_hub/infrastructure/providers image-code/tests
git commit -m "feat(image): 统一注入全局质量约束" -m "在同步与异步 GPT Image 请求的最终边界组合全局质量策略、业务提示词和负向提示词，确保所有生图入口覆盖且不污染任务历史。"
```

---

## Task 2: 重构为普通与 4K Provider 共享的 API Key 轮换池

**Files:**

- Create: `image-code/src/design_hub/infrastructure/providers/api_key_pool.py`
- Modify: `image-code/src/design_hub/infrastructure/providers/openai_compat.py`
- Modify: `image-code/src/design_hub/infrastructure/providers/apinebula_async.py`
- Modify: `image-code/tests/test_provider_contract.py`
- Modify: `image-code/tests/test_async_provider.py`
- Modify: `image-code/tests/test_provider_resilience.py`

- [ ] **Step 1: 为共享起始游标、重试换 Key 和密钥不泄露写失败测试**

新增以下行为测试：

```python
def test_shared_pool_distributes_new_requests_across_providers() -> None:
    pool = ApiKeyPool(("key-a", "key-b", "key-c"))

    first = pool.reserve()
    second = pool.reserve()

    assert pool.key_for(first, 0) == "key-a"
    assert pool.key_for(second, 0) == "key-b"
    assert pool.key_for(first, 1) == "key-b"


def test_api_key_pool_rejects_empty_keys() -> None:
    with pytest.raises(ValueError, match="API key"):
        ApiKeyPool(())


def test_api_key_pool_repr_does_not_expose_secrets() -> None:
    pool = ApiKeyPool(("secret-a", "secret-b"))

    assert "secret-a" not in repr(pool)
    assert "secret-b" not in repr(pool)
```

Provider 测试使用同一 `ApiKeyPool` 创建普通与 4K 两个同步运行时 Provider，发起两个逻辑请求并检查 Authorization 分别使用第一、第二把 Stub Key。429/5xx/transport 重试应换下一把；400 不重试；异常字符串不得包含 Key。保留但不参与运行时组装的异步任务适配器也继续接受 `key_pool` 并单独测试。

- [ ] **Step 2: 运行测试确认旧 Provider 独立游标不满足要求**

Run:

```bash
cd image-code
uv run pytest tests/test_provider_contract.py tests/test_async_provider.py tests/test_provider_resilience.py -q
```

Expected: FAIL，`ApiKeyPool` 不存在且 Provider 构造器仍接收各自的 `api_keys`。

- [ ] **Step 3: 实现线程安全语义明确的共享轮换池**

实现不可打印密钥、每个逻辑请求只领取一次起始位置的对象：

```python
class ApiKeyPool:
    def __init__(self, keys: tuple[str, ...]) -> None:
        normalized = tuple(key.strip() for key in keys if key.strip())
        if not normalized:
            raise ValueError("at least one API key is required")
        self._keys = normalized
        self._next_index = 0

    def reserve(self) -> int:
        index = self._next_index
        self._next_index = (self._next_index + 1) % len(self._keys)
        return index

    def key_for(self, start_index: int, attempt: int) -> str:
        return self._keys[(start_index + attempt) % len(self._keys)]

    def __repr__(self) -> str:
        return f"ApiKeyPool(size={len(self._keys)})"
```

应用由单一 asyncio event loop 组装和调用；不要增加兼容旧 `api_keys` 参数的 adapter。所有 Provider 构造器统一接收 `key_pool: ApiKeyPool`，运行时 composition 把同一个实例交给普通与 4K 两个同步 Provider，并更新所有调用点和测试夹具。

- [ ] **Step 4: 让一次逻辑请求内的重试围绕同一个 reservation**

每个同步运行时请求只 `reserve()` 一次，随后按 attempt 围绕该 reservation 轮换。保留异步适配器的提交在进入 POST 重试循环前也只调用一次 `reserve()`；提交换 Key 成功后轮询从成功 offset 开始，轮询重试只推进本地 offset，不推进全局游标。确定性 4xx 直接抛出，网络类错误继续受现有重试预算限制。

- [ ] **Step 5: 运行 Provider 回归与静态检查**

Run:

```bash
cd image-code
uv run pytest tests/test_provider_contract.py tests/test_async_provider.py tests/test_provider_resilience.py -q
uv run ruff check src tests
uv run mypy src
```

Expected: PASS；两个 Provider 共享游标，重试轮换，错误和 `repr` 不泄露 Key。

- [ ] **Step 6: 提交共享密钥池重构**

```bash
git add image-code/src/design_hub/infrastructure/providers image-code/tests
git commit -m "refactor(image): 共享模型 API Key 轮换池" -m "让普通与 4K 同步运行时 Provider 共享逻辑请求游标，并在可重试错误时轮换密钥，同时修正保留异步适配器的本地轮询偏移。"
```

---

## Task 3: 注册双模型、固定 Images API 请求契约与运行时单价

**Files:**

- Modify: `image-code/src/design_hub/domain/enums.py`
- Modify: `image-code/src/design_hub/config/settings.py`
- Modify: `image-code/src/design_hub/composition.py`
- Modify: `image-code/src/design_hub/infrastructure/providers/openai_compat.py`
- Create: `image-code/tests/test_image_model_composition.py`
- Modify: `image-code/tests/test_provider_contract.py`
- Modify: `image-code/tests/test_provider_resilience.py`
- Modify: `image-code/tests/test_model_config.py`

- [ ] **Step 1: 为双模型注册、固定价格、无 4K seed 和 payload 写失败测试**

测试必须断言：

```python
assert ModelName.GPT_IMAGE_2_4K.value == "gpt-image-2-4k"
assert defaults["gpt-image-2"].unit_cost == Decimal("0.05")
assert "gpt-image-2-4k" not in defaults
assert registry.get(ModelName.GPT_IMAGE_2).reference_mode == "bytes"
assert registry.get(ModelName.GPT_IMAGE_2_4K).reference_mode == "bytes"
assert registry.get(ModelName.GPT_IMAGE_2).unit_cost == Decimal("0.05")
assert registry.get(ModelName.GPT_IMAGE_2_4K).unit_cost == Decimal("0.18")
```

对 4K Provider 捕获请求，断言：

```python
assert payload["model"] == "gpt-image-2-4k"
assert payload["size"] == "3840x2160"
assert payload["quality"] == "high"
assert payload["n"] == 1
```

同时覆盖 generation 与 edit；传入非 `(3840, 2160)` 或 `n != 1` 时在发起 HTTP 前抛 `ValueError`。用假时钟验证整个可重试流程不会超过 `gpt_image_4k_timeout=1800.0` 后再开始新的长请求。

- [ ] **Step 2: 运行测试确认当前只有普通模型**

Run:

```bash
cd image-code
uv run pytest tests/test_image_model_composition.py tests/test_provider_contract.py tests/test_provider_resilience.py tests/test_model_config.py -q
```

Expected: FAIL，枚举、默认配置和 4K Provider 尚未注册。

- [ ] **Step 3: 增加 4K 领域枚举和超时配置**

```python
class ModelName(StrEnum):
    GPT_IMAGE_2 = "gpt-image-2"
    GPT_IMAGE_2_4K = "gpt-image-2-4k"
    # existing models remain unchanged
```

在 `Settings` 增加 `gpt_image_4k_timeout: float = 1800.0`，校验其大于 0。定义不可被 `unit_costs` 覆盖的运行时固定价格映射：普通 `Decimal("0.05")`、4K `Decimal("0.18")`。Mock registry 同样尊重这两个固定价；`default_model_configs()` 只 seed 普通模型，不 seed 4K。

- [ ] **Step 4: 将单 Provider 构建函数重构为双 Provider 构建**

删除 `build_gpt_image_provider()`，实现同签名风格的
`build_gpt_image_providers(settings, unit_costs=None, default_config=None) ->
tuple[AbstractModelProvider, AbstractModelProvider]`。该函数只调用一次
`_resolve_image_connection()`，再用解析出的 Key 创建一个 `ApiKeyPool`：

- 第一项为 `OpenAICompatImageProvider`，领域名 `GPT_IMAGE_2`、上游模型使用解析出的
  普通 model、固定价格 `Decimal("0.05")`、timeout 为 300 秒，尺寸/质量/张数由调用方
  传入；根据是否有参考图分别调用同步 generations/edits。
- 第二项为 `OpenAICompatImageProvider`，领域名 `GPT_IMAGE_2_4K`、上游模型固定
  `gpt-image-2-4k`、固定价格 `Decimal("0.18")`、timeout 与
  max_elapsed 都使用 `settings.gpt_image_4k_timeout`、required_size 为
  `(3840, 2160)`、required_quality 为 `high`、required_count 为 `1`；响应格式、
  input fidelity 和图片存储沿用同步 Provider 现有组装参数。

`build_registry()` 遍历注册返回值，不保留旧函数兼容层。连接地址和 Key 只解析一次；默认
连接必须声明 `provider_type=openai_compat_image`，不兼容时 fail-fast。传入的
`unit_costs` 只影响非固定价模型，数据库旧 `0.40` 不得覆盖两个运行时 Provider。

- [ ] **Step 5: 运行双模型组装和 Provider 测试**

Run:

```bash
cd image-code
uv run pytest tests/test_image_model_composition.py tests/test_provider_contract.py tests/test_provider_resilience.py tests/test_model_config.py -q
uv run ruff check src tests
uv run mypy src
```

Expected: PASS；普通和 4K 均为同步 Images API Provider、共享同一 pool，固定价格不受
数据库旧值影响、默认配置无 4K seed，固定请求契约正确。

- [ ] **Step 6: 提交双模型组装**

```bash
git add image-code/src/design_hub/domain/enums.py image-code/src/design_hub/config/settings.py image-code/src/design_hub/composition.py image-code/src/design_hub/infrastructure/providers/openai_compat.py image-code/tests
git commit -m "feat(image): 注册普通与 4K 双模型" -m "统一使用同步 Images API，新增固定 3840x2160 的 4K Provider，并将 ¥0.05 与 ¥0.18 固定在运行时 registry、排除 4K 默认 seed。"
```

---

## Task 4: 让任务管线仅在运行时显式携带实际模型

**Files:**

- Modify: `image-code/src/design_hub/application/listing/sizing.py`
- Modify: `image-code/src/design_hub/application/listing/listing_service.py`
- Modify: `image-code/src/design_hub/application/listing/job_launcher.py`
- Modify: `image-code/src/design_hub/application/listing/commands.py`
- Modify: `image-code/tests/test_listing_validation.py`

> **用户最终裁决（取代本 Task 的原持久化设计）：** 只保留 runtime model routing。
> 不向 `listing_job` 持久化 model，不修改历史 summary/detail API，不新增迁移。生产 MySQL
> schema 保持不变，Alembic head 必须仍为 `f3a4b5c6d7e8`。

- [ ] **Step 1: 为运行时模型传递和尺寸约束写失败测试**

覆盖：

```python
assert generation_size(ModelName.GPT_IMAGE_2, "4:3") == (1536, 1152)
assert generation_size(ModelName.GPT_IMAGE_2_4K, "16:9") == (3840, 2160)
with pytest.raises(ValueError, match="16:9"):
    generation_size(ModelName.GPT_IMAGE_2_4K, "4:3")
```

在三个独立用例中分别给 `launch_generate`、`launch_clone`、`launch_edit` 传入
`model=GPT_IMAGE_2_4K`，断言按 4K Provider 的 `reference_mode` 物化输入，并将
model 传入 command。不得增加持久化断言或历史 API `model` 字段断言。

- [ ] **Step 2: 运行测试确认模型仍被硬编码**

Run:

```bash
cd image-code
uv run pytest tests/test_listing_validation.py -q
```

Expected: FAIL，launcher/service/command 仍固定 `GPT_IMAGE_2`。

- [ ] **Step 3: 建立模型感知的尺寸和服务 API**

实现：

```python
def generation_size(model: ModelName, ratio: str) -> tuple[int, int]:
    if model is ModelName.GPT_IMAGE_2_4K:
        if ratio != "16:9":
            raise ValueError("4K generation only supports 16:9")
        return 3840, 2160
    return ratio_to_size(ratio)
```

将 `ListingService.reference_mode()` 改为 `reference_mode(model: ModelName)`；`generate/clone/edit` 增加必传 `model`，使用 `registry.get(model)`，并在 `ListingResult.used_model` 返回同一模型。普通 listing 路由由 launcher 默认参数显式落为 `GPT_IMAGE_2`；Chat 后续传具体模型。

- [ ] **Step 4: 让 command 和 launcher 在运行时携带 model**

`ListingCommand` 增加仅供执行期使用的 `model`；`run()` 使用
`generation_size(self.model, self.req.ratio)`；三种 command 的 `_generate()` 传入
`model`，但 `_start()` 不保存 model。Launcher 三个入口签名统一为：

```python
async def launch_generate(
    self,
    user: AuthUser,
    req: ListingGenerateRequest,
    *,
    model: ModelName = ModelName.GPT_IMAGE_2,
) -> str:
```

`clone`、`edit` 同样处理，且 `reference_mode(model)` 必须在参考图物化前调用。

- [ ] **Step 5: 确认数据库 schema 和历史 API 不变**

不得创建 `listing_job.model`、不得修改历史 repository/schema，也不得新增迁移。只执行：

```bash
cd image-code
uv run alembic heads
```

Expected: 单一 head 仍为 `f3a4b5c6d7e8`。本任务不执行 upgrade/downgrade；如后续在临时
SQLite 做独立迁移冒烟，环境变量必须使用 `DB_URL`，且绝不指向默认、开发或生产数据库。

- [ ] **Step 6: 运行任务管线和静态检查**

Run:

```bash
cd image-code
uv run pytest tests/test_listing_validation.py -q
uv run ruff check src tests
uv run mypy src
```

Expected: PASS；普通页面行为不变，4K 模型在运行时显式贯穿且不进入持久化或历史 API。

- [ ] **Step 7: 提交运行时模型贯穿**

```bash
git add image-code/src/design_hub/application/listing image-code/tests/test_listing_validation.py
git commit -m "feat(listing): 运行时传递实际生图模型" -m "将模型选择从 launcher 贯穿到尺寸和 Provider，不修改 listing_job、历史 API 或数据库 schema。"
```

---

## Task 5: 实现 Chat 确定性 4K 意图、冲突阻断和真实计费

**Files:**

- Create: `image-code/src/design_hub/application/chat/rendering_intent.py`
- Modify: `image-code/src/design_hub/application/chat/ratio_intent.py`
- Modify: `image-code/src/design_hub/application/chat/pending_store.py`
- Modify: `image-code/src/design_hub/application/chat/orchestrator.py`
- Modify: `image-code/src/design_hub/application/chat/system_prompt.py`
- Modify: `image-code/src/design_hub/config/chat_knowledge.md`
- Create: `image-code/tests/test_chat_rendering_intent.py`
- Modify: `image-code/tests/test_chat.py`
- Modify: `image-code/tests/test_chat_harness.py`
- Modify: `image-code/tests/test_chat_ratio_intent.py`
- Modify: `image-web/src/lib/chat.ts`
- Modify: `image-web/src/lib/chat.test.ts`

- [ ] **Step 1: 为 4K 正向、否定、讨论和比例冲突写参数化失败测试**

定义测试契约：

```python
@pytest.mark.parametrize(
    "message",
    ["生成一张 4K 图", "做成 4 k", "超高清4K海报", "生成 3840×2160 图片"],
)
def test_explicit_4k_generation_selects_4k(message: str) -> None:
    decision = decide_chat_rendering(message, auto_ratio="1:1")
    assert decision.model is ModelName.GPT_IMAGE_2_4K
    assert decision.ratio.value == "16:9"


@pytest.mark.parametrize(
    "message",
    [
        "生成高清图片", "不要4K，生成横版", "不要生成 4K 图",
        "不需要做成 4K", "不用改成 4K", "别用 4K", "这不是 4K",
    ],
)
def test_vague_or_negated_4k_stays_standard(message: str) -> None:
    assert decide_chat_rendering(message, "1:1").model is ModelName.GPT_IMAGE_2


@pytest.mark.parametrize("ratio", ["1:1", "3:4", "4:3", "9:16"])
def test_4k_conflicting_ratio_is_rejected_before_cost_confirm(ratio: str) -> None:
    with pytest.raises(ChatRenderingConflict, match="4K"):
        decide_chat_rendering(f"生成 4K，比例 {ratio}", auto_ratio="1:1")
```

另测 `“4K 支持什么比例？”` 在没有写工具时不产生费用确认。`3840x2160` 必须被识别为
4K，而不是落入普通比例解析的“不支持比例”。4K + 2:3 必须返回现有“五种支持比例”
文案，而不是错误声称取消 4K 后即可保留 2:3。LLM 调用前的比例备注对明确、非否定 4K
固定写入 16:9，但只有写工具被选择后才执行确定性冲突响应。

- [ ] **Step 2: 为 Chat 模型能力、价格和跨轮编辑写失败测试**

在 Chat 集成测试中断言：

- 普通请求 `cost_confirm.unit_cost == "0.05"`，pending model 为普通模型。
- 明确 4K 请求 `unit_cost == "0.18"`、ratio 为 16:9、pending model 为 4K。
- 4K + 4:3 只返回说明，不产生 `cost_confirm`、pending action 或 job。
- 缺少 4K 配置行时能力仍可用；配置行存在且 disabled 时返回“4K 当前不可用”。
- 数据库普通/4K 旧价格均不能覆盖费用卡固定 ¥0.05/¥0.18 或额度报价。
- 4K 费用确认后 launcher 收到 `model=GPT_IMAGE_2_4K`。
- 费用卡发出后模型被禁用，确认时重新检查并阻止 launcher。
- 选择上一张 4K 图后只说“把背景改成蓝色”，本轮仍使用普通模型；再次写“4K”才升级。
- 用户取消费用确认时必须匹配 token；陈旧 token 不调用 launcher，也不清除当前 pending。
- 4K 数量超过 3 时，在 tool call、费用卡、pending 和 job 前返回：
  `4K 单次最多生成 3 张，请将本次数量调整为 1–3 张；如需更多，请分批生成。`
- 文本 LLM 在已产生多个 chunk 后失败，先按序回放并持久化 partial assistant，再发送
  error 与 assistant_end。

- [ ] **Step 3: 运行 Chat 测试确认失败**

Run:

```bash
cd image-code
uv run pytest tests/test_chat_rendering_intent.py tests/test_chat_ratio_intent.py tests/test_chat.py tests/test_chat_harness.py -q
```

Expected: FAIL，Chat 仍固定使用普通模型且 pending 不保存模型。

- [ ] **Step 4: 实现统一渲染决策器**

在 `rendering_intent.py` 定义：

```python
@dataclass(frozen=True)
class ChatRenderingDecision:
    model: ModelName
    ratio: ChatRatioDecision


class ChatRenderingConflict(ValueError):
    pass


def decide_chat_rendering(message: str, auto_ratio: str) -> ChatRenderingDecision:
    # 1. 否定 4K 优先；2. 检测明确 4K/3840x2160；
    # 3. 4K 时只接受无显式比例或 16:9；4. 普通时复用 decide_chat_ratio。
```

正向正则只覆盖规格列出的表达；同分句否定优先匹配 `不要生成|不需要做成|无需|不用改成|别用|不是`
等前缀及 `4K/4 k`。识别 4K 后先屏蔽 `3840x2160` 分辨率 token，再调用现有显式比例
抽取，避免将它误判为未知比例。不支持比例对象必须先于 4K 支持比例冲突返回。冲突异常
携带固定用户文案：

```text
4K 当前仅支持 16:9 横版（3840×2160）。你可以选择继续生成 4K 16:9，或取消 4K 后按本次指定比例生成。
```

“是否存在本轮生图/改图意图”继续由现有 Chat tool 判定负责；只有 tool 已决定执行 generate/clone/edit 后才调用渲染决策器，能力讨论不会进入该路径。

- [ ] **Step 5: 将模型快照保存进费用确认并贯穿确认执行**

`PendingAction` 增加 `model: ModelName`，`PendingAction.new()` 必须显式接收 model。Orchestrator 在创建 pending 前：

1. 写工具选中后调用 `decide_chat_rendering()`。
2. 检查 `registry` 存在所选模型；配置行缺失视为无显式禁用，存在时必须 enabled。
3. 用 `registry.get(decision.model).unit_cost * count` 计算固定确认金额，忽略 DB unit cost。
4. 4K count 大于 3 时用固定文案在任何费用/任务事件前终止。
5. 保存 model 与规范化 ratio。

确认消费正确 token 后，再次检查 registry 与显式 enabled 状态，然后 `_launch()` 使用
`pending.model` 调用对应 launcher。取消也通过 `PendingStore.take()` 校验 token，错误
token 保留有效 pending。删除 orchestrator 的固定 `image_model` 字段，防止后续路径误用
普通价。账户能力说明使用 registry 固定价格，只用模型配置决定显式启停。

- [ ] **Step 6: 更新 Chat 系统规则、知识与欢迎语**

系统 prompt 和知识文件明确：

- 全品类，不要求品类确认。
- 用户表达完整生图/改图需求后直接进入生成流程。
- 4K 必须本轮明确写出，且只支持 16:9。
- 不主动把“高清”升级为 4K。
- 不向用户展示内部模型名。

前端欢迎语使用已确认文本：

```ts
export const CHAT_WELCOME_COPY =
  '我可以基于你上传的图片制作全品类主图、场景图、卖点图、海报、Logo/品牌视觉，也支持爆款复刻和连续编辑。普通出图支持多种比例；如需 4K，请在需求中明确写出“4K”，4K 当前仅支持 16:9 横版。上传至少 1 张图片，再告诉我想做什么即可。'
```

- [ ] **Step 7: 运行 Chat、前端文案和静态检查**

Run:

```bash
cd image-code
uv run pytest tests/test_chat_rendering_intent.py tests/test_chat_ratio_intent.py tests/test_chat.py tests/test_chat_harness.py -q
uv run ruff check src tests
uv run mypy src
cd ../image-web
npm test -- --run src/lib/chat.test.ts
npm run typecheck
npm run lint
```

Expected: PASS；4K 冲突和三张上限发生在计费前，普通/4K 固定价格不受旧 DB 值影响，
确认 token、确认前能力重检和晚发 LLM 错误顺序均满足契约。

- [ ] **Step 8: 提交 Chat 4K 路由**

```bash
git add image-code/src/design_hub/application/chat image-code/src/design_hub/config/chat_knowledge.md image-code/tests image-web/src/lib/chat.ts image-web/src/lib/chat.test.ts
git commit -m "feat(chat): 按明确意图路由 4K 生图" -m "在费用确认前确定模型与比例，阻断 4K 非 16:9 冲突，保存模型快照并按真实单价启动任务，同时更新新对话能力说明。"
```

---

## Task 6: 保活长 Chat 流并收口取消任务

**Files:**

- Modify: `image-code/src/design_hub/interface/api/routes/chat.py`
- Modify: `image-code/src/design_hub/interface/api/asgi.py`
- Modify: `image-code/src/design_hub/application/listing/listing_service.py`
- Modify: `image-code/src/design_hub/application/listing/commands.py`
- Create: `image-code/tests/test_chat_sse.py`
- Create: `image-code/tests/test_listing_cancellation.py`
- Modify: `image-code/tests/test_listing_history_persistence.py`

- [ ] **Step 1: 写长等待与取消的失败测试**

测试必须证明：

- Chat event source 暂无事件时可用缩短测试间隔产出 `: keep-alive\n\n`，之后仍从同一
  source 收到真实事件，不能每次心跳取消并重建 `anext()`。
- 生成、复刻和编辑在 Provider 已开始且成本已预扣后被 task cancel，均调用一次 rollback，
  然后对调用方重新抛出 `asyncio.CancelledError`。
- Listing command 在 `_generate` 或持久化阶段被取消时，先落失败终态、再发送
  `TASK_FAILED`，随后重新抛出取消。
- 启动 reaper 阈值至少 45 分钟；30 分钟的在飞任务不扫，超过 45 分钟的僵尸任务扫为失败。

- [ ] **Step 2: 实现 20 秒 SSE comment 心跳**

用一个持久 `asyncio.Task` 包裹当前 `anext()`。`asyncio.wait(..., timeout=20)` 超时时只
yield comment，不取消 task；真实事件完成后序列化原 SSE。客户端断开时取消并 await
pending task，再关闭上游 async iterator。`/chat/messages` 与 `/chat/confirm` 共用该 helper。

- [ ] **Step 3: 提高无 schema reaper 阈值**

在 ASGI composition 定义 `STALE_JOB_REAP_AFTER = timedelta(minutes=45)` 并用于启动
`reap_stale()`。注释和正式设计必须说明取舍：覆盖最长 4K 三张批次和余量，避免误杀；
进程崩溃留下的死任务最多比旧 15 分钟阈值晚约 30 分钟恢复。不增加队列、lease 或迁移。

- [ ] **Step 4: 显式处理 `CancelledError`**

`ListingGenerationService.generate/clone/edit` 在预扣后的 Provider/reconcile await 收到
取消时先 rollback；`ListingCommand.run` 的出图段和持久化段分别先调用既有 `_fail`
（refunded 语义保持正确），再 `raise`。不要用吞掉 `BaseException` 的兼容层。

- [ ] **Step 5: 运行韧性回归**

```bash
cd image-code
uv run pytest tests/test_chat_sse.py tests/test_listing_cancellation.py tests/test_listing_history_persistence.py tests/test_provider_resilience.py -q
uv run ruff check src tests
uv run mypy src
```

Expected: PASS；长流持续保活，预扣后取消无余额泄漏、无“生成中”僵尸，45 分钟边界正确。

---

## Task 7: 统一前端固定价格并更新正式文档

**Files:**

- Modify: `image-web/src/lib/listing.ts`
- Modify: `image-web/src/lib/home.ts`
- Modify: `image-web/src/components/listing/ListingConfigPanel.tsx`
- Modify: `image-web/src/pages/style-preview/preview-data.ts`
- Modify/Create: 对应 Vitest
- Modify: 本设计与实施计划

- [ ] **Step 1: 先将前端价格断言改为 ¥0.05**

`estimateCost(1)`、首页单图入口和开发预览 fixture 都必须断言 `0.05/¥0.05`，观察旧
`0.40` 实现失败。协议解析或历史记录夹具若不验证价格行为，可继续使用任意金额。

- [ ] **Step 2: 以一个估算来源更新实际 UI**

`LISTING_UNIT_COST = 0.05`；工作台单图标签、首页快捷入口与样式预览统一通过
`estimateCost(1).toFixed(2)` 展示，避免继续复制价格字面量。运行时代码不得残留用户可见
`¥0.40`。

- [ ] **Step 3: 更新正式设计和计划**

文档必须明确：两个运行时模型都用同步 Images API、共享 pool；固定价独立于持久价格；
无 4K seed 行；Chat 最大 3 张及精确文案；20 秒 heartbeat；45 分钟 reaper 及较慢死任务
恢复取舍；预扣后取消的退款/失败清理。

- [ ] **Step 4: 运行前端聚焦验证**

```bash
cd image-web
npm test -- --run src/lib/listing.test.ts src/lib/home.test.ts src/pages/style-preview/preview-data.test.ts
npm run lint
npm run typecheck
```

Expected: PASS；实际 UI 统一显示普通固定价 ¥0.05。

---

## Task 8: 验证已安全配置的本地三 Key，并完成全量验收

**Files:**

- Inspect locally only: `image-code/.env`（已由 controller 安全配置；gitignored，不修改、不提交）
- No committed source files unless verification exposes a defect

- [ ] **Step 1: 确认 `.env` 被忽略且不会进入 Git**

Run:

```bash
git check-ignore image-code/.env
git status --short
```

Expected: 第一条输出 `image-code/.env`；状态中没有 `.env`。

- [ ] **Step 2: 只验证已安全配置的三 Key 元数据**

controller 已将三把 Key 安全写入 gitignored 的 worktree `.env`。本 Task 不再合并、写入或
改动本地 Key，只验证 `.env` 被忽略、权限为 `600`，并让安全检查只输出：

```text
image-code/.env permission=600
GPT_IMAGE_API_KEY count=3
```

不得在文档、命令或报告中写入 Key 值；不得使用 `set -x`、回显环境变量或任何会打印值的
命令。

- [ ] **Step 3: 验证 registry 固定价格，不更新数据库数据**

用户最终裁决已取代原“通过模型配置服务幂等更新本地价格”步骤。本任务不得更新默认、
开发或生产持久数据库中的任何数据；只通过 registry 固定价和测试验证普通模型 ¥0.05、
4K 模型 ¥0.18，并验证 4K 不进入默认 seed。一次性 `mktemp` SQLite 仅供 mock 启动
fixture 使用。

- [ ] **Step 4: 运行后端全量 CI**

Run:

```bash
cd image-code
uv run pytest -q
uv run ruff check src tests
uv run mypy src
```

Expected: 全部 PASS。

- [ ] **Step 5: 运行前端全量 CI**

Run:

```bash
cd image-web
npm test
npm run lint
npm run typecheck
npm run build
```

Expected: 全部 PASS，生产构建成功。

- [ ] **Step 6: 做一次密钥和全局策略污染审计**

Run:

```bash
git grep -n -E 'sk-[A-Za-z0-9]{16,}' -- . ':!image-code/docs/superpowers/specs/2026-07-25-global-image-quality-4k-chat-design.md'
git grep -n '【全局真实性与细节质量约束】' -- image-code/src
git status --short
```

Expected: 第一条无输出；第二条只命中策略模块及必要测试引用，不命中业务 prompt 构造或持久化层；工作树只包含预期源码改动，`.env` 不出现。

- [ ] **Step 7: 本地启动并做不付费的 Chat 手工验收**

在隔离工作树启动后端与前端，使用 Mock/HTTP Stub 验证。数据库必须是一次性 `mktemp`
SQLite fixture；现有 mock 启动流程可在其中初始化既有 schema 并执行 `seed_defaults`，
验收后必须停止进程并删除临时数据库。这些临时写入不属于持久数据库更新，也不改变项目
schema：

1. 新 Chat 欢迎语说明全品类、至少上传一张图、4K 需明确写出且仅 16:9。
2. “生成横版商品图”仍走普通 4:3，确认价 ¥0.05。
3. “生成 4K 商品图”走 16:9，确认价 ¥0.18。
4. “生成 4K 4:3 商品图”只返回冲突说明，不出现确认卡。
5. “不要 4K，生成 1:1”走普通 1:1。
6. 选择生成结果连续编辑但本轮未写 4K，走普通模型；本轮再次写 4K 才升级。
7. 保存的业务 prompt 不含全局策略全文；不验收任务历史模型字段。

不点击会触发真实上游付费请求的确认动作；如必须做 1 张真实 4K 回归，先暂停并重新取得用户授权。

- [ ] **Step 8: 提交因验收修复产生的独立改动**

若全量验收暴露缺陷，先补回归测试并使用对应 `fix:` 提交；若无源码变化则不创建空提交。最后执行：

```bash
git status --short
git log --oneline --decorate -8
```

Expected: 工作树干净，任务 1–7 的提交均存在。

---

## Task 9: 用户本地确认后的生产发布检查点

本任务不是当前实现阶段的自动动作。只有用户完成本地验收并明确要求上线生产后执行。

- [ ] **Step 1: 使用 `superpowers:finishing-a-development-branch` 检查分支收尾选项**

确认目标分支和用户要求的 dev/prod 流程，不自行推送或部署。

- [ ] **Step 2: 发布前准备代码回滚点**

按现有 SOP 创建可回滚镜像；本需求不变更数据库 schema 或模型配置数据。

- [ ] **Step 3: 安全更新生产三 Key**

生产 `.env` 只保留三 Key 去重列表，只报告 Key 数量。本需求不更新生产模型配置数据。

- [ ] **Step 4: 部署并验证**

确认 Alembic head 仍为 `f3a4b5c6d7e8`，不执行数据库迁移；发布 API 和前端。验证健康
端点、普通/4K 固定运行时价格、欢迎语、4K 冲突、运行时模型路由和错误退款路径。

- [ ] **Step 5: 失败时完整回滚**

代码/容器回到发布前镜像。由于本需求不修改数据库 schema 或数据，无数据库 downgrade
或运营价格恢复步骤。密钥池无需回滚，除非生产密钥验证本身失败。

---

## Final Specification Coverage Checklist

- [ ] 普通与 4K 两个同步运行时 Provider 的 generation/edit 请求只注入一次全局全品类质量策略。
- [ ] 业务 prompt 和历史 prompt 不包含全局策略。
- [ ] 普通与 4K Provider 共享三 Key 游标，重试规则与密钥保密满足规格。
- [ ] 普通模型 ¥0.05、4K 模型 ¥0.18 固定在 registry，旧 DB 价格不能覆盖，且无 4K 默认 seed 行。
- [ ] 4K 固定 3840×2160、16:9、high、n=1、1800 秒且不降级。
- [ ] Chat 只在本轮明确 4K 且确有生图/改图意图时升级。
- [ ] 4K 与 1:1、3:4、4:3、9:16 冲突在费用确认和任务创建前阻断。
- [ ] 4K + 其他不支持比例沿用五种支持比例文案；Chat 4K 单次最多 3 张并使用固定超限文案。
- [ ] 连续编辑不继承上一轮 4K。
- [ ] 缺少 4K 配置行不禁用能力；显式禁用、确认前重检和取消 token 校验均生效。
- [ ] 实际模型通过费用确认快照在运行时贯穿 launcher、Provider 和费用流程，不进入 `listing_job` 或历史 API。
- [ ] Chat 每 20 秒发送 SSE comment 心跳，启动 reaper 为 45 分钟，预扣后取消先退款/失败终结再重抛。
- [ ] 前端工作台、首页和预览的普通价格统一为 ¥0.05。
- [ ] 生产 MySQL schema 不变、不新增迁移，Alembic head 保持 `f3a4b5c6d7e8`。
- [ ] 新对话欢迎语说明全品类能力、至少一张图、4K 明示条件及 16:9 限制。
- [ ] 后端 pytest/Ruff/Mypy 与前端 Vitest/ESLint/TypeScript/build 全部通过。
- [ ] 本地验收前不触发新的真实付费请求，生产发布前再次获得用户明确授权。
