# 三处最小收口实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 修正 Chat 模型选择知识、按真实渲染档位分类 4K 超时，并用聚焦证据关闭已经交付的验收单。

**Architecture:** Chat 的静态知识只描述稳定入口和职责，运行时模型目录仍由现有模型目录 API 负责。管理后台通过 `model_call.generation_item_id` 关联现有 `generation_item.render_tier`，不新增字段或迁移。验收只运行与三处收口直接相关的测试和生产只读烟测。

**Tech Stack:** Python 3.12、FastAPI、SQLAlchemy 2、Pytest、MySQL/SQLite、React 19、Vitest、Markdown 问题黑板

## Global Constraints

- 不新增功能入口，不修改 API/OpenAPI 契约，不新增数据库字段或 Alembic 迁移。
- 不新增模型查询工具、RAG、兼容层、回退逻辑或历史模型名映射。
- 不发起付费生图，不修改生产图片审核状态，不输出凭据、完整提示词或签名 URL 查询参数。
- 只运行聚焦测试、修改文件 Ruff、项目 MyPy 和生产只读烟测；不运行完整前端构建或无关 CI。
- 知识库不硬编码动态可用模型清单，可用项以页面从管理员配置读取的目录为准。
- 任一验证失败即停止关单，不吞错、不以文档状态掩盖失败。
- 每个任务完成后立即按 `type: description` 格式独立提交，提交正文写明改动原因。

---

## 文件结构

- `image-code/src/design_hub/config/chat_knowledge.md`：平台能力与入口的静态知识事实源。
- `image-code/src/design_hub/application/chat/system_prompt.py`：将知识库与工具约束组装为 Chat System Prompt。
- `image-code/tests/test_chat_harness.py`：保护知识库真实性与 System Prompt 契约。
- `image-code/src/design_hub/infrastructure/db/admin_console_repo.py`：统一计算模型调用的管理后台有效状态。
- `image-code/tests/test_admin_console.py`：覆盖普通图片、4K、Wan 和 Chat 的超时分类。
- `image-issues/ISSUE-0069-换背景与反推提示词实现.md`：记录聚焦验收证据并关单。
- `image-issues/ISSUE-0070-管理后台验收.md`：记录管理后台聚焦验收证据并关单。
- `image-issues/ISSUE-0071-生产密钥部署配置.md`：同步生产已生效但运维模板未完成的真实状态，不关闭。

---

### Task 1: 修正 Chat 模型选择知识

**Files:**
- Modify: `image-code/tests/test_chat_harness.py:27-58`
- Modify: `image-code/src/design_hub/config/chat_knowledge.md:27-34`
- Modify: `image-code/src/design_hub/application/chat/system_prompt.py:45-70`

**Interfaces:**
- Consumes: `load_chat_knowledge() -> str` 与 `build_system_prompt(knowledge: str) -> str`。
- Produces: 与当前统一模型选择器一致的静态知识；不改变任何 Python 函数签名或 HTTP 契约。

- [ ] **Step 1: 把当前错误入口变成失败测试**

在 `test_chat_knowledge_removes_stale_capability_claims` 中删除旧的正向断言，并加入以下契约：

```python
def test_chat_knowledge_removes_stale_capability_claims() -> None:
    knowledge = load_chat_knowledge()

    for stale in (
        "按张扣积分",
        "右上角「内测免费」",
        "用户在创作页面选择要使用的模型",
        "引导其回创作页面完成选择",
    ):
        assert stale not in knowledge

    for current in (
        "统一模型选择器",
        "文本模型",
        "图片模型",
        "反推提示词",
        "以页面当前显示的可用模型为准",
        "钱包与价格信息目前暂未公开",
    ):
        assert current in knowledge
```

在 `test_build_system_prompt_has_four_segments_and_embeds_knowledge` 中增加：

```python
assert "Chat 统一模型选择器" in p
assert "不得自行更换、猜测或代为选择" in p
assert "用户在创作页面选择" not in p
```

- [ ] **Step 2: 运行测试并确认旧内容导致失败**

Run:

```bash
cd image-code
uv run pytest tests/test_chat_harness.py -q
```

Expected: 新增的“统一模型选择器”正向断言和旧入口反向断言失败；其他知识库测试保持通过。

- [ ] **Step 3: 修改知识库为稳定事实**

将 `chat_knowledge.md` 的模型段改为以下含义，保持 Markdown 结构和现有 Token 预算：

```markdown
## 模型、钱包与价格
- **统一模型选择器**：Chat 输入框旁的同一个下拉可分别选择文本模型和图片模型。文本模型负责对话与反推提示词；图片模型负责生图、换背景、爆款复刻和二次编辑。其他创作工作台只需要选择图片模型。
- **可用模型**：可选项来自管理员当前启用的模型配置，以页面当前显示的可用模型为准。系统不会替用户选择或自动切换模型。
- **钱包与价格**：钱包与价格信息目前暂未公开。用户询问时如实说明这一点，不猜测、不承诺。
```

删除把 GPT Image 2.0、Wan 2.7 Image Pro 说成固定完整清单的句子。功能章节中涉及具体模型能力的事实，例如“4K 当前仅支持 GPT Image 2.0”，继续保留，因为它描述能力约束而非动态目录清单。

- [ ] **Step 4: 同步 System Prompt 的模型选择约束**

把 `build_system_prompt()` 工具契约中的旧句子：

```text
图像模型由用户在创作页面选择；本轮只能使用用户选择的模型，不得自行更换、猜测或代为选择。
```

替换为：

```text
文本模型和图像模型由用户在 Chat 统一模型选择器中分别选择；本轮只能使用用户选择的模型，
不得自行更换、猜测或代为选择，也不得要求用户离开 Chat 页面完成模型切换。
```

不向 LLM 注入模型目录，不增加工具或额外数据库查询。

- [ ] **Step 5: 运行聚焦验证**

Run:

```bash
cd image-code
uv run pytest tests/test_chat_harness.py -q
uv run ruff check src/design_hub/application/chat/system_prompt.py tests/test_chat_harness.py
```

Expected: 两条命令退出码为 0；知识库测试不再依赖固定可用模型清单。项目级 MyPy 在 Task 2 的 Python 改动完成后统一执行一次。

- [ ] **Step 6: 提交知识库收口**

```bash
git add image-code/src/design_hub/config/chat_knowledge.md \
  image-code/src/design_hub/application/chat/system_prompt.py \
  image-code/tests/test_chat_harness.py
git commit -m "fix: align chat knowledge with model selector" \
  -m "Describe the unified Chat text and image model selector as the current entry point. Keep dynamically enabled models out of static knowledge so administrator changes cannot make the guidance stale."
```

---

### Task 2: 按渲染档位分类 4K 调用超时

**Files:**
- Modify: `image-code/tests/test_admin_console.py:1-25, 430-590`
- Modify: `image-code/src/design_hub/infrastructure/db/admin_console_repo.py:1-45, 795-834`

**Interfaces:**
- Consumes: `ModelCallRow.generation_item_id`, `GenerationItemRow.id`, `GenerationItemRow.render_tier`, `RenderTier.FOUR_K.value`。
- Produces: `SqlAlchemyAdminConsoleRepository._effective_call_status(now: datetime) -> SQL expression`，签名保持不变。

- [ ] **Step 1: 增加四种图片调用的测试数据**

在测试导入中增加：

```python
from datetime import UTC, datetime, timedelta

from design_hub.domain.tasking import RenderTier
from design_hub.infrastructure.db.models import GenerationItemRow
```

新增测试 `test_effective_call_status_uses_generation_item_render_tier`。使用 `_admin_database()` 后，在同一事务插入四个生成项：

```python
now = datetime.now(UTC)
items = (
    ("standard-young", RenderTier.STANDARD, now - timedelta(minutes=7), "apinebula", "gpt-image-2"),
    ("four-k-young", RenderTier.FOUR_K, now - timedelta(minutes=7), "apinebula", "gpt-image-2"),
    ("four-k-stale", RenderTier.FOUR_K, now - timedelta(minutes=32), "apinebula", "gpt-image-2"),
    ("wan-standard", RenderTier.STANDARD, now - timedelta(minutes=7), "dashscope", "wan2.7-image-pro"),
)
```

每个 `GenerationItemRow` 使用 `job-0`、唯一 `sequence` 和 `operation_id`，填入：

```python
{
    "id": item_id,
    "job_id": "job-0",
    "sequence": sequence,
    "render_tier": tier.value,
    "operation_type": ModelOperation.IMAGE_GENERATION.value,
    "final_prompt": "test prompt",
    "model": model,
    "ratio": "16:9" if tier is RenderTier.FOUR_K else "1:1",
    "size": "3840x2160" if tier is RenderTier.FOUR_K else "1024x1024",
    "seed": sequence,
    "reference_snapshot": [],
    "reserved_cost": Decimal("0"),
    "status": "processing",
    "operation_id": f"operation-{item_id}",
}
```

随后为每个生成项插入 `ModelCallRow`，设置相同 `generation_item_id`、对应 `provider/model/started_at`，并统一使用 `status=started`。

- [ ] **Step 2: 断言当前实现错误分类 4K**

测试通过 `repository.list_model_calls(ModelCallFilter(status="uncertain"), limit=50, offset=0)` 查询，断言：

```python
uncertain_ids = {item.call_id for item in page.items}
assert "standard-young-call" in uncertain_ids
assert "wan-standard-call" in uncertain_ids
assert "four-k-stale-call" in uncertain_ids
assert "four-k-young-call" not in uncertain_ids
```

Run:

```bash
cd image-code
uv run pytest tests/test_admin_console.py::test_effective_call_status_uses_generation_item_render_tier -q
```

Expected: FAIL，因为当前代码按不存在的 `gpt-image-2-4k` 判断，`four-k-young-call` 被错误归入 `uncertain`。

- [ ] **Step 3: 用相关子查询识别 4K**

在 `admin_console_repo.py` 导入 `RenderTier`，保持现有 `GenerationItemRow` 导入不变：

```python
from design_hub.domain.tasking import RenderTier
```

在 `_effective_call_status` 内构造：

```python
is_four_k = (
    select(GenerationItemRow.id)
    .where(
        GenerationItemRow.id == ModelCallRow.generation_item_id,
        GenerationItemRow.render_tier == RenderTier.FOUR_K.value,
    )
    .exists()
)
```

将图片调用分支改为：

```python
or_(
    and_(
        is_four_k,
        ModelCallRow.started_at < now - _FOUR_K_IMAGE_STALE_AFTER,
    ),
    and_(
        ~is_four_k,
        ModelCallRow.started_at < now - _IMAGE_STALE_AFTER,
    ),
)
```

完全删除 `"gpt-image-2-4k"` 字面量，不增加按模型名或尺寸判断的备用路径。

- [ ] **Step 4: 运行新的分类测试**

Run:

```bash
cd image-code
uv run pytest tests/test_admin_console.py::test_effective_call_status_uses_generation_item_render_tier -q
```

Expected: PASS。

- [ ] **Step 5: 验证管理后台统计和 MySQL SQL 生成无回归**

Run:

```bash
cd image-code
uv run pytest tests/test_admin_console.py -q
uv run ruff check src/design_hub/infrastructure/db/admin_console_repo.py tests/test_admin_console.py
uv run mypy
```

Expected: 全部退出码为 0；现有 MySQL join 编译测试继续通过，普通图片、Chat 和调用汇总断言无变化。

- [ ] **Step 6: 检查代码中不再存在管理统计旧模型名**

Run:

```bash
rg -n 'gpt-image-2-4k' image-code/src/design_hub/infrastructure/db/admin_console_repo.py
```

Expected: 无输出，退出码为 1。

- [ ] **Step 7: 提交 4K 分类收口**

```bash
git add image-code/src/design_hub/infrastructure/db/admin_console_repo.py \
  image-code/tests/test_admin_console.py
git commit -m "fix: classify 4k calls by render tier" \
  -m "Use the generation item's persisted render tier as the source of truth for stale-call thresholds. Remove the obsolete virtual 4K model-name check without adding schema or compatibility logic."
```

---

### Task 3: 聚焦验收并更新问题黑板

**Files:**
- Modify: `image-issues/ISSUE-0069-换背景与反推提示词实现.md`
- Modify: `image-issues/ISSUE-0070-管理后台验收.md`
- Modify: `image-issues/ISSUE-0071-生产密钥部署配置.md`

**Interfaces:**
- Consumes: Task 1、Task 2 的提交，生产版本 `59112c0`，现有管理员与普通用户 Bearer 凭据。
- Produces: 可复核的测试和生产只读证据；ISSUE-0069、ISSUE-0070 关闭；ISSUE-0071 保持由运维处理。

- [ ] **Step 1: 运行三处收口的后端聚焦回归**

Run:

```bash
cd image-code
uv run pytest \
  tests/test_chat_harness.py \
  tests/test_admin_console.py \
  tests/test_background_replacement.py \
  tests/test_reverse_prompt.py \
  tests/test_runtime_logs.py \
  -q
```

Expected: 全部测试通过。若失败，停止关单并保留失败测试名，不执行 Step 4 之后的状态修改。

- [ ] **Step 2: 运行前端聚焦回归**

Run:

```bash
cd image-web
npm test -- \
  src/components/models/UnifiedChatModelSelector.test.ts \
  src/components/listing/BackgroundConfigPanel.test.ts \
  src/components/chat/ChatResultBlock.test.ts \
  src/pages/AdminOverviewPage.test.ts \
  src/pages/AdminGenerationsPage.test.ts \
  src/pages/AdminRuntimeLogsPage.test.ts
```

Expected: 六个测试文件全部通过。因为没有前端代码或契约变更，不运行完整前端构建。

- [ ] **Step 3: 对生产执行只读烟测**

通过现有安全凭据流程把管理员和普通用户 Bearer 注入当前进程，然后执行以下前置检查；不得把值写入文件或命令历史：

```bash
CLOSURE_BASE_URL="https://image.sepaitech.com"
: "${CLOSURE_ADMIN_BEARER:?secure manager bearer is required}"
: "${CLOSURE_USER_BEARER:?secure user bearer is required}"
closure_result_dir="$(mktemp -d)"
```

依次请求并只打印 HTTP 状态：

```bash
curl -sS -o "${closure_result_dir}/home.html" -w 'home %{http_code}\n' \
  "${CLOSURE_BASE_URL}/"
curl -sS -o "${closure_result_dir}/users.json" -w 'users %{http_code}\n' \
  -H "Authorization: Bearer ${CLOSURE_ADMIN_BEARER}" \
  "${CLOSURE_BASE_URL}/api/admin/users?limit=1&offset=0"
curl -sS -o "${closure_result_dir}/images.json" -w 'images %{http_code}\n' \
  -H "Authorization: Bearer ${CLOSURE_ADMIN_BEARER}" \
  "${CLOSURE_BASE_URL}/api/admin/images?limit=1&offset=0"
curl -sS -o "${closure_result_dir}/calls.json" -w 'calls %{http_code}\n' \
  -H "Authorization: Bearer ${CLOSURE_ADMIN_BEARER}" \
  "${CLOSURE_BASE_URL}/api/admin/model-calls?limit=1&offset=0"
curl -sS -o "${closure_result_dir}/logs.json" -w 'logs %{http_code}\n' \
  -H "Authorization: Bearer ${CLOSURE_ADMIN_BEARER}" \
  "${CLOSURE_BASE_URL}/api/admin/runtime-logs?limit=1&offset=0"
curl -sS -o "${closure_result_dir}/chat-models.json" -w 'chat-models %{http_code}\n' \
  -H "Authorization: Bearer ${CLOSURE_USER_BEARER}" \
  "${CLOSURE_BASE_URL}/api/models/chat"
curl -sS -o "${closure_result_dir}/image-models.json" -w 'image-models %{http_code}\n' \
  -H "Authorization: Bearer ${CLOSURE_USER_BEARER}" \
  "${CLOSURE_BASE_URL}/api/models/image"
```

Expected: 七个请求均返回 200。仅在本地临时目录检查结构：

```bash
jq -e '.items | type == "array"' "${closure_result_dir}/users.json"
jq -e '.items | type == "array"' "${closure_result_dir}/images.json"
jq -e '.items | type == "array"' "${closure_result_dir}/calls.json"
jq -e '.items | type == "array"' "${closure_result_dir}/logs.json"
jq -e 'type == "array" and length > 0' "${closure_result_dir}/chat-models.json"
jq -e 'type == "array" and length > 0' "${closure_result_dir}/image-models.json"
```

不得打印 JSON 正文；不得调用任何 PUT、POST 或 DELETE 管理接口。

- [ ] **Step 4: 关闭 ISSUE-0069**

将 frontmatter 更新为：

```yaml
status: 已关闭
owner: —
updated: 2026-08-03
```

在处理记录追加一条；测试命令的原始输出是数量证据，问题单只记录全部通过，不重复抄写容易出错的数量：

```markdown
- 2026-08-03 [开发] 本轮规定的后端与前端聚焦回归全部通过；生产页面与模型目录只读烟测 200。沿用本单已有真实 APINebula 5/5 与真实 Chat 模型证据，未新增付费调用。换背景边界仍为主体清晰、背景可分离的商品图，复杂海报文字不纳入保真承诺。状态=已关闭，owner=—
```

- [ ] **Step 5: 关闭 ISSUE-0070**

将 frontmatter 更新为：

```yaml
status: 已关闭
owner: —
updated: 2026-08-03
```

追加：

```markdown
- 2026-08-03 [开发] 管理权限、用户管理、图片审核、模型调用统计和运行日志聚焦回归通过；生产用户、图片、模型调用和运行日志列表只读烟测均为 200，写操作闭环由隔离测试数据库验证，未修改真实用户审核状态。对应生产基线 `59112c0`，状态=已关闭，owner=—
```

- [ ] **Step 6: 纠正 ISSUE-0071 但不关闭**

只更新 `updated: 2026-08-03` 并追加：

```markdown
- 2026-08-03 [开发] 收口核对：生产 API/Worker 已使用同一持久 RSA 密钥并通过重启后的动态模型读取；但 `image-ops/deploy/.env.example` 仍未声明 `REQUIRE_PERSISTENT_SECRET_CIPHER=true` 与持久 `AUTH_RSA_PRIVATE_KEY_PEM` 注入方式。该单保持 status=已确认、owner=运维，待运维在其目录补齐模板后关闭。
```

不得修改 `image-ops` 文件，遵守角色写入边界。

- [ ] **Step 7: 检查问题单状态与敏感信息**

Run:

```bash
rg -n '^(status|owner|updated):|2026-08-03 \[开发\]' \
  image-issues/ISSUE-0069-换背景与反推提示词实现.md \
  image-issues/ISSUE-0070-管理后台验收.md \
  image-issues/ISSUE-0071-生产密钥部署配置.md
rg -n 'sk-|Bearer |Authorization:|api[_ -]?key|PRIVATE KEY' \
  image-issues/ISSUE-0069-换背景与反推提示词实现.md \
  image-issues/ISSUE-0070-管理后台验收.md \
  image-issues/ISSUE-0071-生产密钥部署配置.md
git diff --check
```

Expected: 0069、0070 为 `已关闭/—`，0071 为 `已确认/运维`；敏感信息扫描只允许出现配置字段名 `AUTH_RSA_PRIVATE_KEY_PEM`，不得出现任何值、Bearer 或私钥正文；`git diff --check` 通过。

- [ ] **Step 8: 提交验收关账**

```bash
git add \
  image-issues/ISSUE-0069-换背景与反推提示词实现.md \
  image-issues/ISSUE-0070-管理后台验收.md \
  image-issues/ISSUE-0071-生产密钥部署配置.md
git commit -m "docs: close verified admin and image workflow issues" \
  -m "Record focused regression and production read-only evidence for the delivered background, reverse-prompt, and admin-console work. Keep the production-key issue open because the operations template still lacks the required persistent-key declarations."
```

---

## 最终交付检查

完成三个任务后执行以下非全量检查：

```bash
git status --short
git log --oneline -4
git diff main...HEAD --check
```

Expected:

- 工作树干净。
- 设计提交之后恰有三个独立实施提交。
- 与 `main` 的差异只有规格、计划、五个代码/测试文件和三张问题单。
- 没有依赖、迁移、API/OpenAPI、前端组件或 `image-ops` 改动。
