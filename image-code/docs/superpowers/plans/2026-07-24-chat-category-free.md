# Chat Category-Free Generation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 让 Chat 在不推断、不默认、不传递品类的前提下，基于至少一张上传图片和明确意图直接规划出图，并在同一次 Chat LLM 调用中保守完善生图提示词。

**Architecture:** Listing 核心把 `category` 改成可选增强项，并为 `None` 提供与品类无关的基础保真规则；结构化工作台仍可显式使用专项品类规则。Chat 使用独立的 Pydantic 工具参数模型，schema 中完全没有 `category`，再显式转换成 `category=None` 的 Listing 请求。新对话能力说明由前端静态能力卡提供，不创建会话或转录。

**Tech Stack:** Python 3.12、FastAPI、Pydantic 2、Pytest、React 19、TypeScript 6、Vitest、Vite 8。

## Global Constraints

- Chat 不推断、不记录、不默认任何品类，尤其不得默认 `FOOD`。
- Chat 开始生成只要求至少一张上传图片和明确制作意图。
- 未指定张数时默认 1；未指定比例时沿用首图，无法识别时使用 `1:1`。
- Chat LLM 只做保守提示词增强，不新增第二次 LLM 请求或额外确认。
- 不得编造品牌、卖点、文字、人物、道具、数量或品类。
- 费用确认、安全审核、频控、预算守卫和 Provider 保持不变。
- Python 命令只使用 `uv run`；依赖不变。
- 每个任务完成后立即提交，提交信息使用项目既有中文风格且不带 co-author。

---

## File Structure

- Create `image-code/src/design_hub/application/chat/tool_requests.py`
  - 定义 Chat 专属 `ChatGenerateRequest`、`ChatCloneRequest`，并提供到 Listing 请求的显式转换。
- Modify `image-code/src/design_hub/application/listing/requests.py`
  - 将 Listing/Clone 的 `category` 改为无默认值的可选增强项。
- Modify `image-code/src/design_hub/application/listing/prompt_composer.py`
  - 增加基础保真块；无品类时不访问专项品类注册表。
- Modify `image-code/src/design_hub/application/listing/listing_service.py`
  - 让 generate/clone 接受 `category: str | None`。
- Modify `image-code/src/design_hub/application/listing/commands.py`
  - 异步命令和历史快照传递可空品类。
- Modify `image-code/src/design_hub/application/chat/orchestrator.py`
  - 使用 Chat 专属工具 schema/转换，移除品类回显和品类澄清。
- Modify `image-code/src/design_hub/application/chat/system_prompt.py`
  - 固化无品类直接出图与同轮保守提示词增强规则。
- Modify `image-code/src/design_hub/config/chat_knowledge.md`
  - 删除固定五品类范围和 Logo/海报拒绝诱因，写明基于上传图片的全品类视觉能力。
- Modify `image-code/tests/test_listing_validation.py`
  - 覆盖 category=None 的基础保真链和显式品类的专项链。
- Modify `image-code/tests/test_chat.py`
  - 覆盖 Chat 请求转换、任意视觉需求直达费用确认和增强提示词透传。
- Modify `image-code/tests/test_chat_harness.py`
  - 覆盖工具 schema 无 category、系统提示和知识库新约束。
- Modify `image-web/src/lib/chat.ts`
  - 导出欢迎文案和空会话显示判定。
- Modify `image-web/src/lib/chat.test.ts`
  - 覆盖欢迎卡显示条件与文案边界。
- Modify `image-web/src/pages/ChatPage.tsx`
  - 用助手样式能力卡替换单行空状态提示。
- Regenerate `image-web/openapi.json`、`image-web/src/api/schema.d.ts`
  - 同步 Listing category 可选契约。

---

### Task 1: Listing 核心支持真正的无品类生成

**Files:**
- Modify: `image-code/src/design_hub/application/listing/requests.py`
- Modify: `image-code/src/design_hub/application/listing/prompt_composer.py`
- Modify: `image-code/src/design_hub/application/listing/listing_service.py`
- Modify: `image-code/src/design_hub/application/listing/commands.py`
- Test: `image-code/tests/test_listing_validation.py`

**Interfaces:**
- Produces: `ListingGenerateRequest.category: Category | None = None`
- Produces: `CloneRequest.category: Category | None = None`
- Produces: `resolve_fidelity_prompt(category: str | None, registry: CategoryCardRegistry) -> str`
- Consumers: `ListingJobLauncher`、`ListingGenerationService`、Chat 请求转换。

- [ ] **Step 1: 写无品类 Prompt 的失败测试**

在 `test_listing_validation.py` 增加：

```python
def test_category_is_optional_without_food_fallback() -> None:
    req = ListingGenerateRequest(
        upload_ids=["u"], prompt="极简品牌海报", ratio="1:1", n=1
    )
    assert req.category is None

    out = compose_prompt(
        req.prompt,
        {},
        PromptModifierRegistry(),
        category=req.category,
        card_registry=CategoryCardRegistry(),
    )
    assert "参考图是画面主体的唯一事实来源" in out
    assert _FOOD_FIDELITY not in out


def test_explicit_category_keeps_specialized_fidelity() -> None:
    out = compose_prompt(
        "清晨场景",
        {},
        PromptModifierRegistry(),
        category="FOOD",
        card_registry=CategoryCardRegistry(),
    )
    assert _FOOD_FIDELITY in out
```

- [ ] **Step 2: 运行测试并确认 RED**

Run:

```bash
cd image-code
uv run pytest tests/test_listing_validation.py::test_category_is_optional_without_food_fallback -q
```

Expected: FAIL，当前请求仍得到 `category == "FOOD"`。

- [ ] **Step 3: 实现可选品类和基础保真解析**

在 `requests.py`：

```python
category: Category | None = None
```

同时用于 `ListingGenerateRequest` 和 `CloneRequest`。

在 `prompt_composer.py` 增加：

```python
_BASE_REFERENCE_FIDELITY = (
    "参考图是画面主体的唯一事实来源：保持主体结构、轮廓比例、颜色、材质、"
    "已有 Logo 与文字不变，不替换、不翻译、不凭空增删主体内容；"
    "只按照用户明确要求调整构图、背景、光线与整体视觉呈现。"
)


def resolve_fidelity_prompt(
    category: str | None, registry: CategoryCardRegistry
) -> str:
    if category is None:
        return _BASE_REFERENCE_FIDELITY
    return _BASE_REFERENCE_FIDELITY + "\n" + registry.card(category)
```

让 `compose_prompt`、`compose_clone_prompt` 使用 `resolve_fidelity_prompt`，并把签名改成
`category: str | None`。同步把 `ListingGenerationService.generate/clone`、
`ListingGenerationCommand.category`、`CloneCommand.category` 改为 `str | None`。

- [ ] **Step 4: 验证 GREEN 和相关 Listing 回归**

Run:

```bash
cd image-code
uv run pytest tests/test_listing_validation.py tests/test_prompt_cards.py -q
```

Expected: PASS；无品类不包含 `_FOOD_FIDELITY`，显式 `FOOD` 仍包含专项块。

- [ ] **Step 5: 提交核心无品类单元**

```bash
git add image-code/src/design_hub/application/listing image-code/tests/test_listing_validation.py
git commit -m "refactor(listing): 将品类改为可选保真增强" \
  -m "无品类请求使用基础参考图保真规则，不再默认 FOOD；结构化工作台显式品类仍叠加专项保真块。"
```

---

### Task 2: Chat 工具契约彻底移除 category

**Files:**
- Create: `image-code/src/design_hub/application/chat/tool_requests.py`
- Modify: `image-code/src/design_hub/application/chat/orchestrator.py`
- Test: `image-code/tests/test_chat.py`
- Test: `image-code/tests/test_chat_harness.py`

**Interfaces:**
- Consumes: `ListingGenerateRequest(category=None)`、`CloneRequest(category=None)`。
- Produces: `ChatGenerateRequest.to_listing() -> ListingGenerateRequest`
- Produces: `ChatCloneRequest.to_listing() -> CloneRequest`
- Produces: `_tool_specs()` whose generate/clone JSON schemas contain no `category`.

- [ ] **Step 1: 写工具 schema 和转换的失败测试**

在 `test_chat_harness.py` 增加：

```python
def test_chat_write_tool_schemas_never_expose_category() -> None:
    for name in ("generate", "clone"):
        tool = next(item for item in _tool_specs() if item.name == name)
        assert "category" not in tool.parameters["properties"]
```

在 `test_chat.py` 增加：

```python
def test_chat_generate_converts_to_category_free_listing_request() -> None:
    req = ChatOrchestrator._parse_req(
        "generate",
        {
            "upload_ids": ["u"],
            "prompt": "主体居中，柔和棚拍光，保留原图 Logo",
            "ratio": "1:1",
            "n": 1,
        },
    )
    assert isinstance(req, ListingGenerateRequest)
    assert req.category is None
```

- [ ] **Step 2: 运行测试并确认 RED**

Run:

```bash
cd image-code
uv run pytest \
  tests/test_chat_harness.py::test_chat_write_tool_schemas_never_expose_category \
  tests/test_chat.py::test_chat_generate_converts_to_category_free_listing_request -q
```

Expected: FAIL；现有工具 schema 来自 Listing DTO，仍包含 category。

- [ ] **Step 3: 创建 Chat 专属严格参数模型**

`tool_requests.py`：

```python
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, StringConstraints

from design_hub.application.listing.requests import CloneRequest, ListingGenerateRequest

Prompt = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]


class ChatGenerateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    upload_ids: list[str]
    prompt: Prompt
    ratio: str
    n: int | None = None
    plan: dict[str, int] | None = None
    overlay_texts: list[str] | None = None
    modifiers: dict[str, str] = Field(default_factory=dict)

    def to_listing(self) -> ListingGenerateRequest:
        return ListingGenerateRequest(**self.model_dump(), category=None)


class ChatCloneRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    product_upload_ids: list[str]
    reference_upload_ids: list[str]
    clone_mode: str
    ratio: str
    prompt: str = ""
    modifiers: dict[str, str] = Field(default_factory=dict)

    def to_listing(self) -> CloneRequest:
        return CloneRequest(**self.model_dump(), category=None)
```

在 `_tool_specs()` 中让 generate/clone 使用以上模型的 `model_json_schema()`；`_parse_req()` 分别执行
`ChatGenerateRequest(**args).to_listing()` 和 `ChatCloneRequest(**args).to_listing()`。

删除 `_tool_get_job_recipe()` 中的“品类”回显行，防止历史配方重新把品类带回 Chat 上下文。

- [ ] **Step 4: 更新既有 Chat 测试数据并验证 GREEN**

从 `_gen_tc()` 和其他 Chat `ToolCall` 参数中删除 `"category": "FOOD"`。增加一个携带 category 的
工具调用测试，预期被 `extra="forbid"` 拒绝且不会进入费用确认。

Run:

```bash
cd image-code
uv run pytest tests/test_chat.py tests/test_chat_harness.py -q
```

Expected: PASS。

- [ ] **Step 5: 提交 Chat 工具边界单元**

```bash
git add image-code/src/design_hub/application/chat image-code/tests/test_chat.py image-code/tests/test_chat_harness.py
git commit -m "refactor(chat): 从出图工具契约移除品类" \
  -m "新增 Chat 专属严格参数模型并显式转换为 category=None 的 Listing 请求，避免文本模型推断、默认或追问品类。"
```

---

### Task 3: 固化直接出图与同轮保守提示词完善

**Files:**
- Modify: `image-code/src/design_hub/application/chat/system_prompt.py`
- Modify: `image-code/src/design_hub/config/chat_knowledge.md`
- Modify: `image-code/src/design_hub/application/chat/orchestrator.py`
- Test: `image-code/tests/test_chat.py`
- Test: `image-code/tests/test_chat_harness.py`

**Interfaces:**
- Consumes: category-free Chat tool schemas。
- Produces: system prompt that instructs one-pass conservative prompt enhancement.
- Produces: knowledge base that advertises full-category image creation without fixed lists.

- [ ] **Step 1: 写提示词边界和直达费用确认的失败测试**

在 `test_chat_harness.py` 增加：

```python
def test_system_prompt_requires_category_free_conservative_enhancement() -> None:
    prompt = default_system_prompt()
    for forbidden in ("category 默认", "食品 / 服装 / 美妆 / 鞋类 / 数码", "自动识别品类"):
        assert forbidden not in prompt
    for required in (
        "不得询问、推断或填写品类",
        "同一次工具调用",
        "不得编造品牌",
        "不得编造卖点",
        "至少上传一张图片",
    ):
        assert required in prompt
```

在 `test_chat.py` 增加一个带合法 upload id 的 Logo 工具调用，`prompt` 使用保守增强文本：

```python
enhanced = (
    "以用户上传图为主体，设计简洁现代的 Logo 视觉；保持原图已有文字与标识不变，"
    "主体居中，留白充足，使用清晰矢量感边缘，不新增品牌名或宣传文案。"
)
events = await _drain(
    orch.handle_message(USER, None, "帮我做一个简洁现代的 Logo", [uid])
)
confirm = _first(events, "cost_confirm")
assert confirm["args"]["prompt"] == enhanced
assert "category" not in confirm["args"]
```

- [ ] **Step 2: 运行测试并确认 RED**

Run:

```bash
cd image-code
uv run pytest \
  tests/test_chat_harness.py::test_system_prompt_requires_category_free_conservative_enhancement \
  -q
```

Expected: FAIL；当前知识库仍列固定五品类，系统提示仍默认 FOOD 且禁止生成最终提示词。

- [ ] **Step 3: 更新知识库、系统提示和澄清话术**

知识库“支持范围”改为：

```markdown
- **视觉范围**：基于用户上传的图片，可制作任意品类的电商主图、场景图、卖点图、海报、
  Logo / 品牌视觉，也支持爆款复刻与二次编辑。
- **使用前提**：每次创作至少上传 1 张图片，再用自然语言说明想做什么。
```

从“暂不支持”中删除“自动识别品类”，保留视频、素材库等真实未上线能力。

`system_prompt.py` 删除 `category 默认 "FOOD"` 和“prompt 只填用户原话”规则，替换为：

```text
- Chat 不得询问、推断或填写品类；工具参数中不存在 category。
- 用户已上传至少一张图片且说明制作意图后，直接调用 generate；未明确张数时 n=1。
- 在同一次工具调用中保守完善 prompt，只补充构图、背景、光线、镜头、材质、色彩和基础保真。
- 保留用户全部明确约束；不得编造或改动品牌、产品事实、卖点、文字、人物、道具、数量和禁止项。
```

将参数解析失败话术改成只请求“上传图片或说明想做什么”，不得出现产品、品类、风格、比例示例列表。

- [ ] **Step 4: 验证系统提示和 Chat 行为 GREEN**

Run:

```bash
cd image-code
uv run pytest tests/test_chat.py tests/test_chat_harness.py -q
```

Expected: PASS；Logo/海报/未枚举视觉需求的测试均直达 `cost_confirm`。

- [ ] **Step 5: 提交 Chat 行为单元**

```bash
git add image-code/src/design_hub/application/chat image-code/src/design_hub/config/chat_knowledge.md image-code/tests/test_chat.py image-code/tests/test_chat_harness.py
git commit -m "feat(chat): 同轮保守完善全品类出图需求" \
  -m "用户上传图片并说明意图后直接规划出图；Chat LLM 在同一次工具调用中补足必要视觉语言，同时禁止品类判断和过度改写。"
```

---

### Task 4: 新对话展示能力卡

**Files:**
- Modify: `image-web/src/lib/chat.ts`
- Modify: `image-web/src/lib/chat.test.ts`
- Modify: `image-web/src/pages/ChatPage.tsx`

**Interfaces:**
- Produces: `CHAT_WELCOME_COPY: string`
- Produces: `shouldShowChatWelcome(state: ChatState): boolean`
- Consumed by: `ChatPage` empty-session rendering.

- [ ] **Step 1: 写欢迎卡文案和显示条件失败测试**

在 `chat.test.ts` 增加：

```typescript
describe('new chat capability card', () => {
  it('shows only for an idle empty session and describes unrestricted visual scope', () => {
    const empty = initialChatState()
    expect(shouldShowChatWelcome(empty)).toBe(true)
    expect(CHAT_WELCOME_COPY).toContain('任意品类')
    expect(CHAT_WELCOME_COPY).toContain('至少 1 张图片')
    expect(CHAT_WELCOME_COPY).toContain('Logo')
    expect(CHAT_WELCOME_COPY).not.toContain('食品、服装、美妆、鞋类、数码')

    expect(shouldShowChatWelcome(pushUserMessage(empty, '做一张海报'))).toBe(false)
    expect(shouldShowChatWelcome({ ...empty, streaming: true })).toBe(false)
  })
})
```

- [ ] **Step 2: 运行测试并确认 RED**

Run:

```bash
cd image-web
npm run test -- src/lib/chat.test.ts
```

Expected: FAIL，两个导出尚不存在。

- [ ] **Step 3: 实现纯状态接口和助手能力卡**

在 `chat.ts`：

```typescript
export const CHAT_WELCOME_COPY =
  '我可以基于你上传的图片，制作任意品类的电商主图、场景图、卖点图、海报和 Logo/品牌视觉，也支持爆款复刻与二次编辑。上传至少 1 张图片，再告诉我想做什么即可。'

export function shouldShowChatWelcome(state: ChatState): boolean {
  return state.bubbles.length === 0 && !state.streaming
}
```

`ChatPage.tsx` 使用 `shouldShowChatWelcome(state)`，把原单行提示替换为左对齐助手气泡；气泡文本只引用
`CHAT_WELCOME_COPY`，不复制文案。点击“新对话”后 `initialChatState()` 自动恢复该卡，加载有转录的历史
会话时不显示。

- [ ] **Step 4: 验证 GREEN、类型和 lint**

Run:

```bash
cd image-web
npm run test -- src/lib/chat.test.ts
npm run typecheck
npm run lint
```

Expected: PASS。

- [ ] **Step 5: 提交欢迎卡单元**

```bash
git add image-web/src/lib/chat.ts image-web/src/lib/chat.test.ts image-web/src/pages/ChatPage.tsx
git commit -m "feat(chat): 新对话展示全品类能力说明" \
  -m "空会话以助手能力卡说明需上传至少一张图片以及支持的主图、场景图、卖点图、海报、Logo、复刻和编辑能力。"
```

---

### Task 5: 同步契约并完成全量验证

**Files:**
- Regenerate: `image-web/openapi.json`
- Regenerate: `image-web/src/api/schema.d.ts`
- Verify: all changed files.

**Interfaces:**
- Consumes: optional Listing/Clone category OpenAPI schema。
- Produces: synchronized frontend generated types and a release-ready branch.

- [ ] **Step 1: 重新生成 OpenAPI 与 TypeScript schema**

Run:

```bash
cd image-code
uv run python -c 'import json; from design_hub.interface.api.asgi import create_production_app; print(json.dumps(create_production_app().openapi(), ensure_ascii=False, indent=2))' > ../image-web/openapi.json
cd ../image-web
npm run gen:api
```

Expected: `ListingGenerateRequest.category` 和 `CloneRequest.category` 变为 optional nullable；枚举值不变。

- [ ] **Step 2: 提交生成契约**

```bash
git add image-web/openapi.json image-web/src/api/schema.d.ts
git commit -m "chore(api): 同步可选品类请求契约" \
  -m "重新生成 OpenAPI 与 TypeScript 类型，使结构化工作台继续显式传品类，同时允许 Chat 生成 category=None 的请求。"
```

- [ ] **Step 3: 运行后端完整门禁**

Run:

```bash
cd image-code
uv run ruff check .
uv run mypy
uv run pytest
```

Expected: Ruff、Mypy 通过；Pytest 至少 `179 passed`，新增测试全部通过。

- [ ] **Step 4: 运行前端完整门禁和生产构建**

Run:

```bash
cd image-web
npm run lint
npm run typecheck
npm run test
npm run build
```

Expected: ESLint、TypeScript、Vitest 和 Vite build 全部通过。

- [ ] **Step 5: 静态回归扫描**

Run:

```bash
rg -n "食品.*服装.*美妆.*鞋类.*数码|category 默认|默认 FOOD|自动识别品类" \
  image-code/src/design_hub/application/chat \
  image-code/src/design_hub/config/chat_knowledge.md \
  image-web/src/pages/ChatPage.tsx \
  image-web/src/lib/chat.ts
```

Expected: no matches。

- [ ] **Step 6: 本地启动并人工验收**

Backend:

```bash
cd image-code
uv run alembic upgrade head
uv run uvicorn design_hub.interface.api.asgi:app --host 127.0.0.1 --port 8000
```

Frontend:

```bash
cd image-web
npm run dev -- --host 127.0.0.1 --port 3000
```

验收：

1. 新对话立即显示能力卡。
2. 不上传图片发送“做一个 Logo”时，只提醒至少上传一张图片。
3. 上传图片后发送“做一个简洁现代的 Logo”，直接出现 1 张费用确认卡，不询问品类。
4. 费用确认参数不含 category，prompt 为保守增强版本。
5. 不执行真实付费出图，除非用户明确要求。

- [ ] **Step 7: 最终状态检查**

Run:

```bash
git status --short
git log --oneline --decorate -8
```

Expected: 只有明确保留的本地运行产物被忽略，所有业务变更均已按任务提交。
