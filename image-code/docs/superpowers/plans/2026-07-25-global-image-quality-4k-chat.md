# Global Image Quality Policy and Chat 4K Routing Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 为所有真实 GPT Image 请求统一注入全品类真实性与细节质量约束，并让 Chat 仅在用户本轮明确要求 4K 时按固定 16:9、¥0.18/张调用 `gpt-image-2-4k`；普通请求继续按原比例规则和 ¥0.05/张调用 `gpt-image-2`。

**Architecture:** 在 Provider 最终请求边界统一组合全局质量策略、业务提示词和负向提示词；普通异步 Provider 与 4K 同步 Provider 共用一个无密钥泄露的轮换池。Chat 在计费前通过确定性解析器同时决定模型与比例，并将所选模型保存在费用确认快照中，确认后仅在运行时传递到 launcher、Provider 和费用流程。

**Tech Stack:** Python 3.12、FastAPI、Pydantic、SQLAlchemy 2、Alembic、httpx、pytest、Ruff、Mypy；React 19、TypeScript、Vite、Vitest、ESLint。

## Global Constraints

- 严格遵循已确认规格：`image-code/docs/superpowers/specs/2026-07-25-global-image-quality-4k-chat-design.md`。
- 不在源码、测试、文档、迁移、提交消息或命令输出中写入三把 API Key；只安全更新 gitignored 环境文件，并且只验证 Key 数量。
- 不把全局质量策略写回用户消息、`listing_job.prompt` 或其他历史字段。
- 普通模型继续支持现有五种比例；4K 只允许 `3840x2160`（16:9）、`quality=high`、`n=1`。
- 4K 失败不得降级到普通模型。确定性 4xx 立即失败；仅 429、5xx、传输错误可在 1800 秒总墙钟预算内换 Key 重试。
- 用户最终裁决已取代原持久化/迁移方案：模型只做运行时路由和费用确认快照传递，不写入 `listing_job` 或历史 API，不新增迁移；生产 MySQL schema 与 Alembic head `f3a4b5c6d7e8` 保持不变。
- 本需求不更新默认、开发或生产持久数据库及其数据；普通 ¥0.05、4K ¥0.18 只验证代码默认和测试。可启动性冒烟允许使用一次性 `mktemp` SQLite 测试 fixture，让现有 mock 启动流程初始化既有 schema 并执行 `seed_defaults`，验收后停止进程并删除临时数据库；这不属于持久数据库更新，也不改变项目 schema。
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

在同步与异步 Provider 合约测试中分别抓取 generation/edit HTTP payload，断言最终 `prompt` 含全局策略一次、业务 prompt 一次、negative 位于末尾。另在 listing 历史测试中断言数据库保存的仍是原业务 prompt。

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

删除 `_openai_common.py` 中旧的负向提示拼接职责；同步、异步 Provider 在构造网络 payload 时都只调用 `compose_image_api_prompt()`。不要在 listing service 或 Chat orchestrator 中提前注入。

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

Provider 测试使用同一 `ApiKeyPool` 创建普通异步和同步 Provider，发起两个逻辑请求并检查 Authorization 分别使用第一、第二把 Stub Key。429/5xx/transport 重试应换下一把；400 不重试；异常字符串不得包含 Key。

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

应用由单一 asyncio event loop 组装和调用；不要增加兼容旧 `api_keys` 参数的 adapter。同步和异步 Provider 构造器统一改为 `key_pool: ApiKeyPool`，并更新所有调用点和测试夹具。

- [ ] **Step 4: 让一次逻辑请求内的重试围绕同一个 reservation**

普通异步提交在进入 POST 重试循环前调用一次 `reserve()`；同一任务后续轮询沿用该起始 Key，不在每次 GET 时推进全局游标。同步请求同样只 reserve 一次，随后按 attempt 轮换。确定性 4xx 直接抛出，网络类错误继续受现有重试预算限制。

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
git commit -m "refactor(image): 共享模型 API Key 轮换池" -m "让普通异步与同步图片 Provider 共享逻辑请求游标，并在可重试错误时轮换密钥，移除各 Provider 独立轮换和轮询推进热点。"
```

---

## Task 3: 注册双模型、固定 4K 请求契约并配置真实单价

**Files:**

- Modify: `image-code/src/design_hub/domain/enums.py`
- Modify: `image-code/src/design_hub/config/settings.py`
- Modify: `image-code/src/design_hub/composition.py`
- Modify: `image-code/src/design_hub/infrastructure/providers/openai_compat.py`
- Create: `image-code/tests/test_image_model_composition.py`
- Modify: `image-code/tests/test_provider_contract.py`
- Modify: `image-code/tests/test_provider_resilience.py`
- Modify: `image-code/tests/test_model_config.py`

- [ ] **Step 1: 为双模型注册、默认价格和 4K payload 写失败测试**

测试必须断言：

```python
assert ModelName.GPT_IMAGE_2_4K.value == "gpt-image-2-4k"
assert defaults["gpt-image-2"].unit_cost == Decimal("0.05")
assert defaults["gpt-image-2-4k"].unit_cost == Decimal("0.18")
assert registry.get(ModelName.GPT_IMAGE_2).reference_mode == "url"
assert registry.get(ModelName.GPT_IMAGE_2_4K).reference_mode == "bytes"
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

在 `Settings` 增加 `gpt_image_4k_timeout: float = 1800.0`，校验其大于 0。更新 `_MOCK_UNIT_COSTS` 和 `default_model_configs()`，普通价格改为 `Decimal("0.05")`，4K 为 `Decimal("0.18")`。

- [ ] **Step 4: 将单 Provider 构建函数重构为双 Provider 构建**

删除 `build_gpt_image_provider()`，实现同签名风格的
`build_gpt_image_providers(settings, unit_costs=None, default_config=None) ->
tuple[AbstractModelProvider, AbstractModelProvider]`。该函数只调用一次
`_resolve_image_connection()`，再用解析出的 Key 创建一个 `ApiKeyPool`：

- 第一项为 `AsyncImageTasksProvider`，领域名 `GPT_IMAGE_2`、上游模型使用解析出的普通
  model、价格使用普通配置、其余端点/轮询/存储参数保持现有值。
- 第二项为 `OpenAICompatImageProvider`，领域名 `GPT_IMAGE_2_4K`、上游模型固定
  `gpt-image-2-4k`、价格读取 4K 配置且缺省为 `Decimal("0.18")`、timeout 与
  max_elapsed 都使用 `settings.gpt_image_4k_timeout`、required_size 为
  `(3840, 2160)`、required_quality 为 `high`、required_count 为 `1`；响应格式、
  input fidelity 和图片存储沿用同步 Provider 现有组装参数。

`build_registry()` 遍历注册返回值，不保留旧函数兼容层。连接地址和 Key 只解析一次；普通模型继续服从现有协议配置，4K 固定同步 Images API。

- [ ] **Step 5: 运行双模型组装和 Provider 测试**

Run:

```bash
cd image-code
uv run pytest tests/test_image_model_composition.py tests/test_provider_contract.py tests/test_provider_resilience.py tests/test_model_config.py -q
uv run ruff check src tests
uv run mypy src
```

Expected: PASS；普通和 4K 均注册、共享同一 pool，默认价格与固定请求契约正确。

- [ ] **Step 6: 提交双模型组装**

```bash
git add image-code/src/design_hub/domain/enums.py image-code/src/design_hub/config/settings.py image-code/src/design_hub/composition.py image-code/src/design_hub/infrastructure/providers/openai_compat.py image-code/tests
git commit -m "feat(image): 注册普通与 4K 双模型" -m "保留普通异步任务协议，新增固定 3840x2160 的同步 4K Provider，并设置 ¥0.05 与 ¥0.18 的新库默认价格和 1800 秒预算。"
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
    ["生成高清图片", "不要4K，生成横版", "无需 4 k，按 1:1 生成"],
)
def test_vague_or_negated_4k_stays_standard(message: str) -> None:
    assert decide_chat_rendering(message, "1:1").model is ModelName.GPT_IMAGE_2


@pytest.mark.parametrize("ratio", ["1:1", "3:4", "4:3", "9:16"])
def test_4k_conflicting_ratio_is_rejected_before_cost_confirm(ratio: str) -> None:
    with pytest.raises(ChatRenderingConflict, match="4K"):
        decide_chat_rendering(f"生成 4K，比例 {ratio}", auto_ratio="1:1")
```

另测 `“4K 支持什么比例？”` 在没有本轮生图/改图意图时不升级。`3840x2160` 必须被识别为 4K，而不是落入普通比例解析的“不支持比例”。

- [ ] **Step 2: 为 Chat 模型能力、价格和跨轮编辑写失败测试**

在 Chat 集成测试中断言：

- 普通请求 `cost_confirm.unit_cost == "0.05"`，pending model 为普通模型。
- 明确 4K 请求 `unit_cost == "0.18"`、ratio 为 16:9、pending model 为 4K。
- 4K + 4:3 只返回说明，不产生 `cost_confirm`、pending action 或 job。
- 4K 配置 disabled 时返回“4K 当前不可用”，不产生费用确认。
- 4K 费用确认后 launcher 收到 `model=GPT_IMAGE_2_4K`。
- 选择上一张 4K 图后只说“把背景改成蓝色”，本轮仍使用普通模型；再次写“4K”才升级。
- 用户取消费用确认时不调用 launcher。

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

正向正则只覆盖规格列出的表达；否定正则优先匹配 `不要|不需要|无需|不用` 后可选空格的 `4K/4 k`。识别 4K 后先屏蔽 `3840x2160` 分辨率 token，再调用现有显式比例抽取，避免将它误判为未知比例。冲突异常携带固定用户文案：

```text
4K 当前仅支持 16:9 横版（3840×2160）。你可以选择继续生成 4K 16:9，或取消 4K 后按本次指定比例生成。
```

“是否存在本轮生图/改图意图”继续由现有 Chat tool 判定负责；只有 tool 已决定执行 generate/clone/edit 后才调用渲染决策器，能力讨论不会进入该路径。

- [ ] **Step 5: 将模型快照保存进费用确认并贯穿确认执行**

`PendingAction` 增加 `model: ModelName`，`PendingAction.new()` 必须显式接收 model。Orchestrator 在创建 pending 前：

1. 调用 `decide_chat_rendering()`。
2. 检查 `registry` 存在所选模型，以及模型配置为 enabled。
3. 用 `registry.get(decision.model).unit_cost * count` 计算确认金额。
4. 保存 model 与规范化 ratio。

确认后 `_launch()` 使用 `pending.model` 调用对应 launcher。删除 orchestrator 的固定 `image_model` 字段，防止后续路径误用普通价。账户能力说明分别读取两个模型配置。

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

Expected: PASS；4K 冲突发生在计费前，普通/4K 价格和确认后模型一致，欢迎语包含明示规则。

- [ ] **Step 8: 提交 Chat 4K 路由**

```bash
git add image-code/src/design_hub/application/chat image-code/src/design_hub/config/chat_knowledge.md image-code/tests image-web/src/lib/chat.ts image-web/src/lib/chat.test.ts
git commit -m "feat(chat): 按明确意图路由 4K 生图" -m "在费用确认前确定模型与比例，阻断 4K 非 16:9 冲突，保存模型快照并按真实单价启动任务，同时更新新对话能力说明。"
```

---

## Task 6: 验证已安全配置的本地三 Key，并完成全量验收

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

- [ ] **Step 3: 验证代码默认价格，不更新数据库数据**

用户最终裁决已取代原“通过模型配置服务幂等更新本地价格”步骤。本任务不得更新默认、
开发或生产持久数据库中的任何数据；只通过代码默认配置和测试验证普通模型 ¥0.05、4K
模型 ¥0.18。一次性 `mktemp` SQLite 仅供 mock 启动 fixture 使用。

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

Expected: 工作树干净，任务 1–5 的提交均存在。

---

## Task 7: 用户本地确认后的生产发布检查点

本任务不是当前实现阶段的自动动作。只有用户完成本地验收并明确要求上线生产后执行。

- [ ] **Step 1: 使用 `superpowers:finishing-a-development-branch` 检查分支收尾选项**

确认目标分支和用户要求的 dev/prod 流程，不自行推送或部署。

- [ ] **Step 2: 发布前准备代码回滚点**

按现有 SOP 创建可回滚镜像；本需求不变更数据库 schema 或模型配置数据。

- [ ] **Step 3: 安全更新生产三 Key**

生产 `.env` 只保留三 Key 去重列表，只报告 Key 数量。本需求不更新生产模型配置数据。

- [ ] **Step 4: 部署并验证**

确认 Alembic head 仍为 `f3a4b5c6d7e8`，不执行数据库迁移；发布 API 和前端。验证健康
端点、普通/4K 代码默认价格、欢迎语、4K 冲突、运行时模型路由和错误退款路径。

- [ ] **Step 5: 失败时完整回滚**

代码/容器回到发布前镜像。由于本需求不修改数据库 schema 或数据，无数据库 downgrade
或运营价格恢复步骤。密钥池无需回滚，除非生产密钥验证本身失败。

---

## Final Specification Coverage Checklist

- [ ] 所有同步/异步、生成/编辑真实 GPT Image 请求只注入一次全局全品类质量策略。
- [ ] 业务 prompt 和历史 prompt 不包含全局策略。
- [ ] 普通与 4K Provider 共享三 Key 游标，重试规则与密钥保密满足规格。
- [ ] 普通模型 ¥0.05、4K 模型 ¥0.18 由代码默认和测试验证，不更新任何数据库数据。
- [ ] 4K 固定 3840×2160、16:9、high、n=1、1800 秒且不降级。
- [ ] Chat 只在本轮明确 4K 且确有生图/改图意图时升级。
- [ ] 4K 与 1:1、3:4、4:3、9:16 冲突在费用确认和任务创建前阻断。
- [ ] 连续编辑不继承上一轮 4K。
- [ ] 实际模型通过费用确认快照在运行时贯穿 launcher、Provider 和费用流程，不进入 `listing_job` 或历史 API。
- [ ] 生产 MySQL schema 不变、不新增迁移，Alembic head 保持 `f3a4b5c6d7e8`。
- [ ] 新对话欢迎语说明全品类能力、至少一张图、4K 明示条件及 16:9 限制。
- [ ] 后端 pytest/Ruff/Mypy 与前端 Vitest/ESLint/TypeScript/build 全部通过。
- [ ] 本地验收前不触发新的真实付费请求，生产发布前再次获得用户明确授权。
