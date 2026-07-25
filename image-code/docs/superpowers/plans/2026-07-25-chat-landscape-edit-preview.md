# Chat Landscape Ratio, Iterative Editing, and Preview Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make Chat deterministically honor supported ratios, map landscape language to `4:3`, let users select any completed result as the next edit source, and preview generated images at their full aspect ratio.

**Architecture:** A pure backend ratio-decision unit owns text/landscape/upload precedence, while the Chat orchestrator owns trusted edit-source injection and write-tool normalization. The frontend keeps unsent edit selection as page-local state, resolves stable image keys through existing owner-scoped job details, and shares focused result/preview components between live and historical Chat output.

**Tech Stack:** Python 3.12, FastAPI, Pydantic 2, Pillow, pytest, React 19, TypeScript 6, TanStack Query, Radix UI, Vitest, Tailwind CSS.

## Global Constraints

- Supported ratios are exactly `1:1`, `3:4`, `4:3`, `9:16`, and `16:9`.
- Ratio precedence is explicit supported numeric ratio > landscape wording (`4:3`) > first uploaded image > `1:1`.
- Unsupported explicit ratios must not silently approximate or enter the paid write-tool flow.
- Selecting an edit source never sends a request, generates an image, or charges the user.
- A paid edit still uses the existing cost-confirmation gate and owner-scoped `source_image_key` resolution.
- Editing without an explicit UI-selected stable image key must never guess a source from an image URL or conversation position.
- Edit requests inherit the source ratio unless the user explicitly requests another supported ratio or landscape layout.
- Existing per-session maximum of 5 generation jobs remains unchanged.
- No new runtime dependencies are required.
- User-facing copy stays Chinese; code comments remain English unless an existing local section is already Chinese.

---

### Task 1: Add deterministic five-ratio decision and GPT Image sizing

**Files:**
- Create: `image-code/src/design_hub/application/chat/ratio_intent.py`
- Modify: `image-code/src/design_hub/application/chat/image_ratio.py`
- Modify: `image-code/src/design_hub/application/listing/sizing.py`
- Modify: `image-code/src/design_hub/infrastructure/providers/mock_text.py`
- Create: `image-code/tests/test_chat_ratio_intent.py`
- Modify: `image-code/tests/test_chat_image_ratio.py`
- Modify: `image-code/tests/test_listing_validation.py`

**Interfaces:**
- Consumes: raw current user text and the existing first-upload fallback ratio.
- Produces: `ChatRatioDecision`, `decide_chat_ratio(message, auto_ratio)`, and the `4:3 -> (1536, 1152)` listing size mapping used by later tasks.

- [ ] **Step 1: Write failing ratio-intent tests**

Create `image-code/tests/test_chat_ratio_intent.py`:

```python
import pytest

from design_hub.application.chat.ratio_intent import (
    ChatRatioSource,
    UnsupportedChatRatio,
    decide_chat_ratio,
)


@pytest.mark.parametrize("text", ["做横版主图", "生成一张横图", "改成横向构图"])
def test_landscape_wording_maps_to_four_by_three(text: str) -> None:
    decision = decide_chat_ratio(text, "1:1")
    assert decision.ratio == "4:3"
    assert decision.source is ChatRatioSource.ORIENTATION
    assert decision.changes_edit_ratio is True


def test_explicit_supported_ratio_overrides_landscape_and_upload() -> None:
    decision = decide_chat_ratio("做横版 16:9 主图", "3:4")
    assert decision.ratio == "16:9"
    assert decision.source is ChatRatioSource.EXPLICIT


def test_upload_ratio_and_square_fallback_are_used_without_text_ratio() -> None:
    inherited = decide_chat_ratio("做一张高级主图", "4:3")
    assert inherited.ratio == "4:3"
    assert inherited.source is ChatRatioSource.AUTO
    assert inherited.changes_edit_ratio is False


def test_unsupported_explicit_ratio_is_preserved_as_user_facing_error() -> None:
    decision = decide_chat_ratio("按 2:3 出图", "1:1")
    with pytest.raises(UnsupportedChatRatio, match="1:1 / 3:4 / 4:3 / 9:16 / 16:9"):
        decision.require_supported()
```

- [ ] **Step 2: Extend existing image and size tests with `4:3`**

Add these assertions:

```python
# image-code/tests/test_chat_image_ratio.py
def test_detects_supported_ratios_and_rounding_error() -> None:
    assert detect_supported_ratio(_png(800, 800)) == "1:1"
    assert detect_supported_ratio(_png(800, 1067)) == "3:4"
    assert detect_supported_ratio(_png(1600, 1200)) == "4:3"
    assert detect_supported_ratio(_png(900, 1600)) == "9:16"
    assert detect_supported_ratio(_png(1600, 900)) == "16:9"


# image-code/tests/test_listing_validation.py
@pytest.mark.parametrize(
    ("ratio", "expected"),
    [
        ("1:1", (1024, 1024)),
        ("3:4", (1152, 1536)),
        ("4:3", (1536, 1152)),
        ("9:16", (864, 1536)),
        ("16:9", (1536, 864)),
    ],
)
def test_ratio_to_size_preserves_requested_aspect_ratio(
    ratio: str, expected: tuple[int, int]
) -> None:
    assert ratio_to_size(ratio) == expected
```

- [ ] **Step 3: Run the focused tests and verify they fail**

Run:

```bash
cd image-code
uv run pytest tests/test_chat_ratio_intent.py tests/test_chat_image_ratio.py tests/test_listing_validation.py -q
```

Expected: collection fails because `ratio_intent` does not exist, and the existing maps do not recognize `4:3`.

- [ ] **Step 4: Implement the pure ratio decision**

Create `image-code/src/design_hub/application/chat/ratio_intent.py`:

```python
import re
from dataclasses import dataclass
from enum import StrEnum

SUPPORTED_CHAT_RATIOS = ("1:1", "3:4", "4:3", "9:16", "16:9")
_SUPPORTED_SET = frozenset(SUPPORTED_CHAT_RATIOS)
_EXPLICIT_RATIO_RE = re.compile(
    r"(?<!\d)([1-9]\d*)\s*(?:[:：/xX×]|比)\s*([1-9]\d*)(?!\d)"
)
_LANDSCAPE_WORDS = ("横版", "横图", "横向构图")


class ChatRatioSource(StrEnum):
    EXPLICIT = "explicit"
    ORIENTATION = "orientation"
    AUTO = "auto"
    UNSUPPORTED = "unsupported"


class UnsupportedChatRatio(ValueError):
    pass


@dataclass(frozen=True)
class ChatRatioDecision:
    ratio: str | None
    source: ChatRatioSource
    requested: str | None = None

    @property
    def changes_edit_ratio(self) -> bool:
        return self.source in {
            ChatRatioSource.EXPLICIT,
            ChatRatioSource.ORIENTATION,
        }

    def require_supported(self) -> str:
        if self.ratio is not None:
            return self.ratio
        options = " / ".join(SUPPORTED_CHAT_RATIOS)
        raise UnsupportedChatRatio(
            f"当前支持的图片比例是 {options}，你写的 {self.requested} 暂不支持，请选择其中一种。"
        )


def decide_chat_ratio(message: str, auto_ratio: str) -> ChatRatioDecision:
    if auto_ratio not in _SUPPORTED_SET:
        raise ValueError(f"无效自动比例：{auto_ratio}")
    match = _EXPLICIT_RATIO_RE.search(message)
    if match is not None:
        requested = f"{match.group(1)}:{match.group(2)}"
        if requested in _SUPPORTED_SET:
            return ChatRatioDecision(requested, ChatRatioSource.EXPLICIT, requested)
        return ChatRatioDecision(None, ChatRatioSource.UNSUPPORTED, requested)
    if any(word in message for word in _LANDSCAPE_WORDS):
        return ChatRatioDecision("4:3", ChatRatioSource.ORIENTATION)
    return ChatRatioDecision(auto_ratio, ChatRatioSource.AUTO)
```

- [ ] **Step 5: Extend upload recognition, listing sizing, and the mock parser**

Apply the exact map additions:

```python
# image-code/src/design_hub/application/chat/image_ratio.py
_SUPPORTED_RATIOS = {
    "1:1": 1 / 1,
    "3:4": 3 / 4,
    "4:3": 4 / 3,
    "9:16": 9 / 16,
    "16:9": 16 / 9,
}


# image-code/src/design_hub/application/listing/sizing.py
_RATIO_TO_SIZE: dict[str, tuple[int, int]] = {
    "1:1": (1024, 1024),
    "3:4": (1152, 1536),
    "4:3": (1536, 1152),
    "9:16": (864, 1536),
    "16:9": (1536, 864),
}
```

Extend the mock provider’s current explicit and automatic ratio regexes without changing the existing
`自动比例=` system-note name yet (Task 2 changes that note atomically with the orchestrator):

```python
_RATIO_RE = re.compile(
    r"(?<!\d)(1|3|4|9|16)\s*(?:[:：xX×]|比)\s*(1|3|4|9|16)(?!\d)"
)
_AUTO_RATIO_RE = re.compile(r"自动比例=(1:1|3:4|4:3|9:16|16:9)")
_SUPPORTED_RATIOS = frozenset({"1:1", "3:4", "4:3", "9:16", "16:9"})
```

- [ ] **Step 6: Run focused tests and quality checks**

Run:

```bash
cd image-code
uv run pytest tests/test_chat_ratio_intent.py tests/test_chat_image_ratio.py tests/test_listing_validation.py -q
uv run ruff check src/design_hub/application/chat/ratio_intent.py src/design_hub/application/chat/image_ratio.py src/design_hub/application/listing/sizing.py tests/test_chat_ratio_intent.py
uv run mypy
```

Expected: all focused tests pass, Ruff reports no issues, and Mypy exits 0.

- [ ] **Step 7: Commit the deterministic ratio unit**

```bash
git add image-code/src/design_hub/application/chat/ratio_intent.py \
  image-code/src/design_hub/application/chat/image_ratio.py \
  image-code/src/design_hub/application/listing/sizing.py \
  image-code/src/design_hub/infrastructure/providers/mock_text.py \
  image-code/tests/test_chat_ratio_intent.py \
  image-code/tests/test_chat_image_ratio.py \
  image-code/tests/test_listing_validation.py
git commit -m "feat(chat): 支持横版与五种确定性比例" \
  -m "新增独立比例决策单元，固定数字比例、横版表达、首图比例和方图兜底的优先级，并补齐 GPT Image 2 的 4:3 尺寸映射。"
```

---

### Task 2: Add trusted Chat edit-source context and write-tool normalization

**Files:**
- Modify: `image-code/src/design_hub/interface/chat_schemas.py`
- Modify: `image-code/src/design_hub/interface/api/routes/chat.py`
- Modify: `image-code/src/design_hub/application/chat/orchestrator.py`
- Modify: `image-code/src/design_hub/application/chat/system_prompt.py`
- Modify: `image-code/src/design_hub/infrastructure/providers/mock_text.py`
- Modify: `image-code/tests/test_chat.py`
- Modify: `image-code/tests/test_chat_harness.py`

**Interfaces:**
- Consumes: `ChatRatioDecision` from Task 1 and optional `edit_source_image_key` from the authenticated Chat request.
- Produces: normalized `generate`/`clone`/`edit` arguments that cannot override the deterministic ratio or UI-selected edit source.

- [ ] **Step 1: Write failing context and normalization tests**

Add imports and tests to `image-code/tests/test_chat.py`:

```python
from design_hub.application.chat.ratio_intent import decide_chat_ratio


def test_prepare_generate_args_forces_deterministic_landscape_ratio() -> None:
    args = ChatOrchestrator._prepare_write_args(
        "generate",
        {"upload_ids": ["u"], "prompt": "主图", "ratio": "1:1", "n": 1},
        decide_chat_ratio("做横版主图", "3:4"),
        None,
    )
    assert args["ratio"] == "4:3"


def test_prepare_edit_args_uses_selected_key_and_inherits_ratio_for_delta() -> None:
    args = ChatOrchestrator._prepare_write_args(
        "edit",
        {
            "source_image_key": "hallucinated.png",
            "prompt": "背景换成海边",
            "edit_mode": "delta",
            "ratio": "1:1",
        },
        decide_chat_ratio("背景换成海边", "1:1"),
        "selected.png",
    )
    assert args == {
        "source_image_key": "selected.png",
        "prompt": "背景换成海边",
        "edit_mode": "delta",
    }


def test_prepare_edit_args_promotes_ratio_change_to_full() -> None:
    args = ChatOrchestrator._prepare_write_args(
        "edit",
        {
            "source_image_key": "wrong.png",
            "prompt": "改成横版",
            "edit_mode": "delta",
        },
        decide_chat_ratio("改成横版", "1:1"),
        "selected.png",
    )
    assert args["source_image_key"] == "selected.png"
    assert args["edit_mode"] == "full"
    assert args["ratio"] == "4:3"


def test_prepare_edit_args_rejects_missing_ui_selection() -> None:
    with pytest.raises(ValueError, match="先在结果图上点击"):
        ChatOrchestrator._prepare_write_args(
            "edit",
            {"source_image_key": "guessed.png", "prompt": "改暖色", "edit_mode": "delta"},
            decide_chat_ratio("改暖色", "1:1"),
            None,
        )


def test_selected_edit_source_is_injected_only_into_llm_context(tmp_path) -> None:
    async def _impl() -> None:
        inf = await _infra(str(tmp_path))
        llm = CapturingTextLLM()
        events = await _drain(
            inf.orch(llm).handle_message(
                USER,
                None,
                "把背景改成海边",
                [],
                edit_source_image_key="selected.png",
            )
        )
        assert "source_image_key=selected.png" in llm.messages[-1].content
        session_id = _first(events, "session")["session_id"]
        transcript = await inf.chat_repo.get_transcript(session_id, USER.user_id)
        assert transcript is not None
        assert transcript.messages[0].content == "把背景改成海边"
        assert transcript.messages[0].attachment_upload_ids == ()

    asyncio.run(_impl())


def test_invalid_selected_source_never_creates_or_charges_a_job(tmp_path) -> None:
    async def _impl() -> None:
        inf = await _infra(str(tmp_path))
        call = ToolCall(
            id="edit-1",
            name="edit",
            arguments={
                "source_image_key": "model-guessed.png",
                "prompt": "改暖色",
                "edit_mode": "delta",
            },
        )
        planned = await _drain(
            inf.orch(StubTextLLM(("好的，我来调整。", (call,)))).handle_message(
                USER,
                None,
                "改暖色",
                [],
                edit_source_image_key="missing.png",
            )
        )
        session_id = _first(planned, "session")["session_id"]
        confirm_token = _first(planned, "cost_confirm")["confirm_token"]
        confirmed = await _drain(
            inf.orch(StubTextLLM(("完成", ()))).handle_confirm(
                USER, session_id, confirm_token, "confirm"
            )
        )
        assert _first(confirmed, "error")["code"] == "bad_request"
        assert await inf.chat_repo.job_count(session_id) == 0
        assert (await inf.ledger.snapshot(USER.user_id)).user_month_used == 0

    asyncio.run(_impl())
```

Replace the old automatic-ratio harness assertions in
`image-code/tests/test_chat_harness.py` with:

```python
from design_hub.application.chat.ratio_intent import decide_chat_ratio


def test_build_system_prompt_uses_determined_ratio_without_asking() -> None:
    prompt = build_system_prompt("KB")
    assert "1:1 / 3:4 / 4:3 / 9:16 / 16:9" in prompt
    assert "本轮确定比例" in prompt
    assert "不要追问比例" in prompt
    assert "未明确套图或张数时，按单图 n=1" in prompt


def test_generate_tool_uses_determined_ratio() -> None:
    generate = next(tool for tool in _tool_specs() if tool.name == "generate")
    assert "确定比例由系统备注提供" in generate.description


def test_current_ratio_and_edit_source_are_added_only_to_latest_user_message() -> None:
    transcript = _transcript(3)
    out = _to_llm_messages(
        transcript,
        current_ratio=decide_chat_ratio("做横版", "3:4"),
        edit_source_image_key="selected.png",
    )
    assert "本轮确定比例=4:3" in out[-1].content
    assert "source_image_key=selected.png" in out[-1].content
    assert all("本轮确定比例=" not in message.content for message in out[:-1])
    assert all("source_image_key=" not in message.content for message in out[:-1])
```

- [ ] **Step 2: Run focused Chat tests and verify they fail**

Run:

```bash
cd image-code
uv run pytest tests/test_chat.py -q
```

Expected: tests fail because `_prepare_write_args` and the new `handle_message` parameter do not exist.

- [ ] **Step 3: Extend the request schema and route**

Update `ChatMessageRequest`:

```python
class ChatMessageRequest(BaseModel):
    session_id: str | None = None
    message: str
    upload_ids: list[str] = Field(default_factory=list)
    edit_source_image_key: str | None = None
```

Pass the new field from the route:

```python
async for event in orch.handle_message(
    user,
    req.session_id,
    req.message,
    req.upload_ids,
    edit_source_image_key=req.edit_source_image_key,
):
    yield _sse(event)
```

- [ ] **Step 4: Inject trusted edit context and normalize write arguments**

In `orchestrator.py`, import Task 1’s types:

```python
from design_hub.application.chat.ratio_intent import (
    ChatRatioDecision,
    UnsupportedChatRatio,
    decide_chat_ratio,
)
```

Change the `_to_llm_messages` signature to:

```python
def _to_llm_messages(
    transcript: ChatTranscript,
    *,
    current_ratio: ChatRatioDecision | None = None,
    edit_source_image_key: str | None = None,
) -> list[ChatMessage]:
```

Replace the existing `if current_auto_ratio is not None:` injection block with:

```python
    notes: list[str] = []
    if current_ratio is not None:
        if current_ratio.ratio is None:
            notes.append(
                f"[系统备注] 用户明确要求比例={current_ratio.requested}，当前不支持；"
                "若用户明确要出图，不要调用写工具，告知支持的五种比例。"
            )
        else:
            notes.append(
                f"[系统备注] 本轮确定比例={current_ratio.ratio}，"
                f"来源={current_ratio.source.value}。调用 generate/clone 时必须原样使用。"
            )
    if edit_source_image_key is not None:
        notes.append(
            "[系统备注] 用户已通过界面明确选定编辑底图 "
            f"source_image_key={edit_source_image_key}。若本轮要求修改图片，必须调用 edit "
            "并原样使用此 key；不得改用 generate 或猜测其他底图。"
        )
    if notes:
        if not out or out[-1].role != "user":
            raise ValueError("本轮系统备注只能注入当前 user 消息")
        current = out[-1]
        out[-1] = ChatMessage(
            role=current.role,
            content=f"{current.content}\n\n" + "\n".join(notes),
            tool_call_id=current.tool_call_id,
            tool_calls=current.tool_calls,
        )
```

Add the normalizer:

```python
@staticmethod
def _prepare_write_args(
    tool: str,
    args: dict[str, Any],
    ratio: ChatRatioDecision,
    edit_source_image_key: str | None,
) -> dict[str, Any]:
    normalized = dict(args)
    if tool in {"generate", "clone"}:
        normalized["ratio"] = ratio.require_supported()
        return normalized
    if tool != "edit":
        return normalized
    if edit_source_image_key is None:
        raise ValueError("请先在结果图上点击「继续编辑」，再告诉我需要怎么修改。")
    normalized["source_image_key"] = edit_source_image_key
    if ratio.changes_edit_ratio:
        normalized["edit_mode"] = "full"
        normalized["ratio"] = ratio.require_supported()
    else:
        normalized.pop("ratio", None)
    return normalized
```

Change the `handle_message` signature to:

```python
async def handle_message(
    self,
    user: AuthUser,
    session_id: str | None,
    message: str,
    upload_ids: list[str],
    *,
    edit_source_image_key: str | None = None,
) -> AsyncIterator[ChatEvent]:
```

Replace its existing `auto_ratio`/`llm_messages` construction with:

```python
    auto_ratio = await self._auto_ratio(user, upload_ids)
    ratio_decision = decide_chat_ratio(message, auto_ratio)
    llm_messages = [
        ChatMessage(role="system", content=self.system_prompt),
        *_to_llm_messages(
            transcript,
            current_ratio=ratio_decision,
            edit_source_image_key=edit_source_image_key,
        ),
    ]
```

Before parsing a write call, normalize it and preserve the unsupported-ratio copy:

```python
try:
    normalized_args = self._prepare_write_args(
        call.name, call.arguments, ratio_decision, edit_source_image_key
    )
    req = self._parse_req(call.name, normalized_args)
except UnsupportedChatRatio as exc:
    clar = str(exc)
    yield ChatEvent("assistant_delta", {"text": clar})
    await self.chat_repo.append_message(
        session_id=session_id, role="assistant", content=clar
    )
    yield ChatEvent("assistant_end", {"status": "complete"})
    return
```

Keep the existing generic `except Exception` validation branch immediately after this specific branch.
Use `normalized_args`, not `call.arguments`, in `tool_call` and `cost_confirm` events.

Change the `generate` tool description in `_tool_specs()` to:

```python
"出图（单图流 n 或套图 plan）。拿到产品图 upload_ids 且用户意图可执行时调用；"
"确定比例由系统备注提供，调用时必须原样使用。未明确套图或张数时按单图 n=1，"
"不要为比例或张数追问。"
```

- [ ] **Step 5: Update the system prompt and local mock edit behavior**

Replace the ratio contract in `system_prompt.py` with:

```text
- ratio 只能取 1:1 / 3:4 / 4:3 / 9:16 / 16:9 之一。
  本轮系统备注给出的“本轮确定比例”是后端已按优先级算出的最终值，调用 generate/clone 时必须原样使用。
- 用户通过界面选中编辑底图时，系统备注会给出 source_image_key。明确修改该图时调用 edit 并原样使用；
  未选图不得猜测底图。未要求改比例时 edit 不传 ratio；要求改比例或横版时用 full 并传确定比例。
```

In `mock_text.py`, add:

```python
_EDIT_SOURCE_RE = re.compile(r"明确选定编辑底图 source_image_key=([^\s。]+)")
_EDIT_INTENT_WORDS = ("改", "换", "调整", "重做", "变成")
_AUTO_RATIO_RE = re.compile(r"本轮确定比例=(1:1|3:4|4:3|9:16|16:9)")
```

Before clone/generate branches, emit an edit call only when a selected key and edit wording both exist:

```python
edit_source = _EDIT_SOURCE_RE.search(text)
user_text = text.partition("\n\n[系统备注]")[0]
if edit_source and any(word in user_text for word in _EDIT_INTENT_WORDS):
    async for chunk in self._stream("好的，我会基于你选中的图片继续调整。"):
        yield chunk
    yield ToolCallChunk((
        ToolCall(
            id="mock_edit",
            name="edit",
            arguments={
                "source_image_key": edit_source.group(1),
                "prompt": user_text,
                "edit_mode": "delta",
            },
        ),
    ))
    return
```

- [ ] **Step 6: Run Chat and prompt harness tests**

Run:

```bash
cd image-code
uv run pytest tests/test_chat.py tests/test_chat_harness.py tests/test_chat_image_ratio.py -q
uv run ruff check src tests/test_chat.py tests/test_chat_harness.py
uv run mypy
```

Expected: all selected tests pass; Ruff and Mypy exit 0.

- [ ] **Step 7: Commit the trusted edit-source backend**

```bash
git add image-code/src/design_hub/interface/chat_schemas.py \
  image-code/src/design_hub/interface/api/routes/chat.py \
  image-code/src/design_hub/application/chat/orchestrator.py \
  image-code/src/design_hub/application/chat/system_prompt.py \
  image-code/src/design_hub/infrastructure/providers/mock_text.py \
  image-code/tests/test_chat.py \
  image-code/tests/test_chat_harness.py
git commit -m "feat(chat): 接入可信图片编辑上下文" \
  -m "Chat 消息接收界面选中的稳定图片标识，并在写工具前强制使用该标识和确定性比例；未选图或不支持比例不会进入费用闸。"
```

---

### Task 3: Extend the frontend contract and stable result state

**Files:**
- Modify: `image-web/openapi.json`
- Modify: `image-web/src/api/schema.d.ts`
- Modify: `image-web/src/api/chat.ts`
- Modify: `image-web/src/lib/chat.ts`
- Modify: `image-web/src/lib/chat.test.ts`
- Create: `image-web/src/api/chat.test.ts`

**Interfaces:**
- Consumes: backend `ChatMessageRequest.edit_source_image_key` and existing `ResultSlot.imageKey`.
- Produces: `ChatEditSource`, `ChatPreviewImage`, `editSourceFromSlot`, `previewImageFromSlot`, request-body mapping, and `ChatState.activeJobId`.

- [ ] **Step 1: Write failing frontend state and request-body tests**

Add to `image-web/src/lib/chat.test.ts`:

```ts
import {
  editSourceFromSlot,
  previewImageFromSlot,
} from '@/lib/chat'

describe('chat result image actions', () => {
  it('creates an edit source only after a stable image key exists', () => {
    expect(editSourceFromSlot({ url: 'https://img/result.png' })).toBeNull()
    expect(
      editSourceFromSlot({
        url: 'https://img/result.png',
        imageKey: 'result.png',
        imageType: '场景',
      }),
    ).toEqual({
      url: 'https://img/result.png',
      imageKey: 'result.png',
      imageType: '场景',
    })
  })

  it('allows preview before a stable edit key exists', () => {
    expect(previewImageFromSlot({ url: 'https://img/live.png' })).toEqual({
      url: 'https://img/live.png',
      imageKey: undefined,
      imageType: undefined,
    })
  })
})
```

Extend the reducer assertion:

```ts
s = feed(s, [{ kind: 'job_started', jobId: 'j1', tool: 'generate', count: 3 }])
expect(s.activeJobId).toBe('j1')
```

Create `image-web/src/api/chat.test.ts`:

```ts
import { describe, expect, it } from 'vitest'

import { buildChatMessageBody } from '@/api/chat'

describe('buildChatMessageBody', () => {
  it('omits edit source for normal chat messages', () => {
    expect(
      buildChatMessageBody({
        sessionId: 's1',
        message: '做一张主图',
        uploadIds: ['u1'],
      }),
    ).toEqual({
      session_id: 's1',
      message: '做一张主图',
      upload_ids: ['u1'],
    })
  })

  it('maps a selected generated image to edit_source_image_key', () => {
    expect(
      buildChatMessageBody({
        sessionId: 's1',
        message: '背景换成海边',
        editSourceImageKey: 'result.png',
      }),
    ).toEqual({
      session_id: 's1',
      message: '背景换成海边',
      upload_ids: [],
      edit_source_image_key: 'result.png',
    })
  })
})
```

- [ ] **Step 2: Run focused frontend tests and verify they fail**

Run:

```bash
cd image-web
npm test -- src/lib/chat.test.ts src/api/chat.test.ts
```

Expected: tests fail because the new types/helpers/body builder and `activeJobId` do not exist.

- [ ] **Step 3: Regenerate the OpenAPI contract**

Run:

```bash
cd image-code
uv run python -c 'import json; from design_hub.interface.api.asgi import create_production_app; print(json.dumps(create_production_app().openapi(), ensure_ascii=False, indent=2))' > ../image-web/openapi.json
cd ../image-web
npm run gen:api
```

Expected: `ChatMessageRequest` in both generated artifacts contains optional `edit_source_image_key`.

- [ ] **Step 4: Add request-body mapping**

Update `SendMessageInput` and add a pure builder in `image-web/src/api/chat.ts`:

```ts
export interface SendMessageInput {
  sessionId: string | null
  message: string
  uploadIds?: string[]
  editSourceImageKey?: string
}

export type ChatMessageBody = components['schemas']['ChatMessageRequest']

export function buildChatMessageBody(input: SendMessageInput): ChatMessageBody {
  const body: ChatMessageBody = {
    session_id: input.sessionId,
    message: input.message,
    upload_ids: input.uploadIds ?? [],
  }
  if (input.editSourceImageKey) {
    body.edit_source_image_key = input.editSourceImageKey
  }
  return body
}

export function sendChatMessage(
  input: SendMessageInput,
  onEvent: (e: ChatEvent) => void,
  signal?: AbortSignal,
) {
  return streamSSE('/chat/messages', buildChatMessageBody(input), onEvent, signal)
}
```

Add this import:

```ts
import type { components } from '@/api/schema'
```

- [ ] **Step 5: Add stable image actions and active job state**

In `image-web/src/lib/chat.ts`, add:

```ts
export interface ChatPreviewImage {
  url: string
  imageKey?: string
  imageType?: string
}

export interface ChatEditSource {
  url: string
  imageKey: string
  imageType?: string
}

export function previewImageFromSlot(slot: ResultSlot): ChatPreviewImage | null {
  if (!slot.url) return null
  return { url: slot.url, imageKey: slot.imageKey, imageType: slot.imageType }
}

export function editSourceFromSlot(slot: ResultSlot): ChatEditSource | null {
  if (!slot.url || !slot.imageKey) return null
  return { url: slot.url, imageKey: slot.imageKey, imageType: slot.imageType }
}
```

Extend `ChatState`:

```ts
export interface ChatState {
  sessionId: string | null
  bubbles: ChatBubble[]
  slots: ResultSlot[]
  activeJobId: string | null
  jobDone: number
  jobTotal: number
  awaiting: CostConfirm | null
  streaming: boolean
  error: { code: string; message: string } | null
}
```

Initialize it and set it on `job_started`:

```ts
export function initialChatState(): ChatState {
  return {
    sessionId: null,
    bubbles: [],
    slots: [],
    activeJobId: null,
    jobDone: 0,
    jobTotal: 0,
    awaiting: null,
    streaming: false,
    error: null,
  }
}

case 'job_started':
  return {
    ...state,
    awaiting: null,
    slots: Array.from({ length: ev.count }, () => ({ url: null }) as ResultSlot),
    activeJobId: ev.jobId,
    jobDone: 0,
    jobTotal: ev.count,
  }
```

- [ ] **Step 6: Run frontend tests, typecheck, and build**

Run:

```bash
cd image-web
npm test -- src/lib/chat.test.ts src/api/chat.test.ts src/lib/listing.test.ts
npm run typecheck
npm run build
```

Expected: all selected tests pass; TypeScript and Vite build exit 0.

- [ ] **Step 7: Commit the frontend contract/state unit**

```bash
git add image-web/openapi.json \
  image-web/src/api/schema.d.ts \
  image-web/src/api/chat.ts \
  image-web/src/api/chat.test.ts \
  image-web/src/lib/chat.ts \
  image-web/src/lib/chat.test.ts
git commit -m "feat(chat): 建立图片编辑选择状态" \
  -m "同步 Chat 编辑源 API 契约，记录当前任务标识，并为预览与编辑区分临时图片 URL 和稳定 image_key。"
```

---

### Task 4: Build the Chat result actions, full-ratio preview, and iterative edit flow

**Files:**
- Create: `image-web/src/components/chat/ChatImagePreviewDialog.tsx`
- Create: `image-web/src/components/chat/ChatResultBlock.tsx`
- Modify: `image-web/src/pages/ChatPage.tsx`
- Modify: `image-web/src/lib/chat.test.ts`

**Interfaces:**
- Consumes: `ChatPreviewImage`, `ChatEditSource`, `activeJobId`, `detailToResultSlots`, and the `editSourceImageKey` field accepted by `sendChatMessage`.
- Produces: clickable full-ratio preview, deterministic “继续编辑” selection, current-job detail hydration, and repeatable edit result cards.

- [ ] **Step 1: Add a failing pure state regression for message submission**

Add this helper and test contract to `image-web/src/lib/chat.ts` and `image-web/src/lib/chat.test.ts` before wiring UI:

```ts
// test
import { consumeChatEditSource } from '@/lib/chat'

it('captures the selected key for one send and clears the composer selection', () => {
  const selected = {
    url: 'https://img/result.png',
    imageKey: 'result.png',
    imageType: '场景',
  }
  expect(consumeChatEditSource(selected)).toEqual({
    editSourceImageKey: 'result.png',
    nextSelection: null,
  })
  expect(consumeChatEditSource(null)).toEqual({
    editSourceImageKey: undefined,
    nextSelection: null,
  })
})
```

Run:

```bash
cd image-web
npm test -- src/lib/chat.test.ts
```

Expected: test fails because `consumeChatEditSource` does not exist.

- [ ] **Step 2: Implement the one-send selection helper**

Add to `image-web/src/lib/chat.ts`:

```ts
export function consumeChatEditSource(source: ChatEditSource | null): {
  editSourceImageKey: string | undefined
  nextSelection: null
} {
  return {
    editSourceImageKey: source?.imageKey,
    nextSelection: null,
  }
}
```

Run:

```bash
cd image-web
npm test -- src/lib/chat.test.ts
```

Expected: the focused Chat tests pass.

- [ ] **Step 3: Create the controlled full-ratio preview**

Create `image-web/src/components/chat/ChatImagePreviewDialog.tsx`:

```tsx
import { useState } from 'react'
import { DownloadIcon, SquarePenIcon } from 'lucide-react'

import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogTitle,
} from '@/components/ui/dialog'
import { downloadImage } from '@/lib/download'
import {
  type ChatEditSource,
  type ChatPreviewImage,
} from '@/lib/chat'

export function ChatImagePreviewDialog({
  image,
  onOpenChange,
  onEdit,
}: {
  image: ChatPreviewImage | null
  onOpenChange: (open: boolean) => void
  onEdit: (source: ChatEditSource) => void
}) {
  const [failedUrl, setFailedUrl] = useState<string | null>(null)
  const loadFailed = image !== null && failedUrl === image.url

  return (
    <Dialog open={image !== null} onOpenChange={onOpenChange}>
      <DialogContent className="flex max-h-[calc(100dvh-2rem)] max-w-[calc(100vw-2rem)] flex-col gap-3 bg-black/90 p-3 sm:max-w-5xl">
        <DialogTitle className="sr-only">图片预览</DialogTitle>
        <DialogDescription className="sr-only">
          按图片原始比例完整预览生成结果
        </DialogDescription>
        <div className="grid min-h-0 flex-1 place-items-center overflow-hidden">
          {image && !loadFailed ? (
            <img
              src={image.url}
              alt={image.imageType ? `${image.imageType}生成结果` : '生成结果'}
              onError={() => setFailedUrl(image.url)}
              className="max-h-[calc(100dvh-8rem)] max-w-full object-contain"
            />
          ) : (
            <p className="py-20 text-sm text-white/75">图片加载失败</p>
          )}
        </div>
        {image && (
          <div className="flex justify-center gap-2">
            {image.imageKey && (
              <button
                type="button"
                onClick={() => {
                  onEdit({
                    url: image.url,
                    imageKey: image.imageKey!,
                    imageType: image.imageType,
                  })
                  onOpenChange(false)
                }}
                className="rounded-full bg-wb-brand px-4 py-2 text-sm font-semibold text-white"
              >
                <SquarePenIcon className="mr-1 inline size-4" />
                继续编辑
              </button>
            )}
            <button
              type="button"
              onClick={() => void downloadImage(image.url, 'chat-result.png')}
              className="rounded-full bg-white px-4 py-2 text-sm font-semibold text-wb-ink-2"
            >
              <DownloadIcon className="mr-1 inline size-4" />
              下载
            </button>
          </div>
        )}
      </DialogContent>
    </Dialog>
  )
}
```

- [ ] **Step 4: Extract the reusable Chat result block**

Create `image-web/src/components/chat/ChatResultBlock.tsx`:

```tsx
import {
  DownloadIcon,
  Loader2Icon,
  SquarePenIcon,
} from 'lucide-react'

import type { ResultSlot } from '@/components/listing/ResultGallery'
import { downloadImage } from '@/lib/download'
import {
  editSourceFromSlot,
  previewImageFromSlot,
  type ChatEditSource,
  type ChatPreviewImage,
} from '@/lib/chat'

export function ChatResultBlock({
  slots,
  done,
  total,
  onPreview,
  onEdit,
}: {
  slots: ResultSlot[]
  done: number
  total: number
  onPreview: (image: ChatPreviewImage) => void
  onEdit: (source: ChatEditSource) => void
}) {
  const generating = done < total && slots.some((slot) => !slot.url && !slot.error)
  return (
    <div className="glass-lite max-w-[88%] rounded-2xl rounded-tl-md p-3">
      <p className="mb-2 px-1 text-[12.5px] font-medium text-wb-ink-3">
        出图结果 <span className="text-wb-ink-6">{done}/{total}</span>
        {generating && (
          <Loader2Icon className="ml-1.5 inline size-3 animate-spin text-wb-brand" />
        )}
      </p>
      <div className="grid grid-cols-2 gap-2 sm:grid-cols-3">
        {slots.map((slot, index) => {
          if (slot.url) {
            const preview = previewImageFromSlot(slot)
            const editSource = editSourceFromSlot(slot)
            return (
              <div
                key={`${slot.imageKey ?? slot.url}-${index}`}
                className="group relative aspect-square overflow-hidden rounded-xl border border-wb-line-1 bg-white"
              >
                <button
                  type="button"
                  onClick={() => preview && onPreview(preview)}
                  className="size-full"
                  aria-label={`预览第 ${index + 1} 张图片`}
                >
                  <img src={slot.url} alt="" className="size-full object-cover" />
                </button>
                <div className="absolute inset-x-1.5 bottom-1.5 flex justify-between gap-1 opacity-100 sm:opacity-0 sm:transition-opacity sm:group-hover:opacity-100">
                  {editSource ? (
                    <button
                      type="button"
                      onClick={() => onEdit(editSource)}
                      className="rounded-lg bg-wb-brand/95 px-2 py-1 text-[11px] text-white"
                    >
                      <SquarePenIcon className="mr-1 inline size-3" />
                      继续编辑
                    </button>
                  ) : <span />}
                  <button
                    type="button"
                    onClick={() =>
                      void downloadImage(
                        slot.url!,
                        `${slot.imageType ?? 'chat'}-${index + 1}.png`,
                      )
                    }
                    className="rounded-lg bg-wb-ink-2/90 px-2 py-1 text-[11px] text-white"
                  >
                    <DownloadIcon className="mr-1 inline size-3" />
                    下载
                  </button>
                </div>
              </div>
            )
          }
          if (slot.error) {
            return (
              <div
                key={index}
                title={slot.error}
                className="grid aspect-square place-items-center rounded-xl border border-dashed border-wb-red-line bg-wb-red-tint p-2 text-center text-[11px] text-wb-red"
              >
                生成失败
              </div>
            )
          }
          return (
            <div
              key={index}
              className="grid aspect-square place-items-center rounded-xl border border-dashed border-wb-line-3 bg-wb-surface-1"
            >
              <div className="size-5 animate-spin rounded-full border-2 border-wb-line-2 border-t-wb-brand" />
            </div>
          )
        })}
      </div>
    </div>
  )
}
```

- [ ] **Step 5: Wire selection, stable job details, preview, and sending in ChatPage**

Update imports in `ChatPage.tsx`:

```tsx
import { ChatImagePreviewDialog } from '@/components/chat/ChatImagePreviewDialog'
import { ChatResultBlock } from '@/components/chat/ChatResultBlock'
import {
  applyChatEvent,
  clearAwaiting,
  consumeChatEditSource,
  initialChatState,
  pushUserMessage,
  sessionMessagesToBubbles,
  type ChatBubble,
  type ChatEditSource,
  type ChatPreviewImage,
  type ChatState,
  type CostConfirm,
} from '@/lib/chat'
```

Add local state:

```tsx
const [selectedEditSource, setSelectedEditSource] = useState<ChatEditSource | null>(null)
const [previewImage, setPreviewImage] = useState<ChatPreviewImage | null>(null)
```

Add one selection function so generated-image editing and new uploads cannot be active at the same time:

```tsx
function selectEditSource(source: ChatEditSource) {
  setAttached([])
  setSelectedEditSource(source)
}
```

At the start of `onPickFiles`, after the empty-list guard, clear the generated-image selection:

```tsx
setSelectedEditSource(null)
```

Clear both states when loading or starting another session:

```tsx
function selectSession(id: string) {
  if (id === stateRef.current.sessionId || loadSession.isPending) return
  abortRef.current?.abort()
  setSelectedEditSource(null)
  setPreviewImage(null)
  loadSession.mutate(id)
}

function newSession() {
  abortRef.current?.abort()
  loadSession.reset()
  setState(initialChatState())
  setDraft('')
  setAttached([])
  setSelectedEditSource(null)
  setPreviewImage(null)
}
```

At the start of `send`, immediately after the existing empty/busy guard, capture the selection:

```tsx
const consumed = consumeChatEditSource(selectedEditSource)
```

Replace the existing local bubble update and composer reset with:

```tsx
  setState((prev) =>
    pushUserMessage(
      prev,
      text,
      uploadIds?.length
        ? attached.map((image) => uploadPreviewUrl(image.url))
        : undefined,
    ),
  )
  setDraft('')
  setAttached([])
  setSelectedEditSource(consumed.nextSelection)
```

Replace the existing `sendChatMessage` call with:

```tsx
  await sendChatMessage(
    {
      sessionId: stateRef.current.sessionId,
      message: text,
      uploadIds,
      editSourceImageKey: consumed.editSourceImageKey,
    },
    on,
    ac.signal,
  )
```

Add a focused current-result wrapper:

```tsx
function CurrentJobResult({
  state,
  onPreview,
  onEdit,
}: {
  state: ChatState
  onPreview: (image: ChatPreviewImage) => void
  onEdit: (source: ChatEditSource) => void
}) {
  const stableJobId = !state.streaming ? state.activeJobId ?? undefined : undefined
  const job = useListingJob(stableJobId)
  const slots = job.data ? detailToResultSlots(job.data) : state.slots
  const done = slots.filter((slot) => slot.url).length
  return (
    <ChatResultBlock
      slots={slots}
      done={job.data ? done : state.jobDone}
      total={job.data ? slots.length : state.jobTotal}
      onPreview={onPreview}
      onEdit={onEdit}
    />
  )
}
```

Change historical `JobResult` to accept the same callbacks and return `ChatResultBlock`:

```tsx
function JobResult({
  jobId,
  onPreview,
  onEdit,
}: {
  jobId: string
  onPreview: (image: ChatPreviewImage) => void
  onEdit: (source: ChatEditSource) => void
}) {
  const query = useListingJob(jobId)
  if (query.isLoading) {
    return (
      <div className="glass-lite flex max-w-[88%] items-center gap-2 rounded-2xl rounded-tl-md px-4 py-3 text-[12.5px] text-wb-ink-6">
        <Loader2Icon className="size-3.5 animate-spin" />
        正在载入出图结果…
      </div>
    )
  }
  if (query.error || !query.data) {
    return (
      <div className="glass-lite max-w-[88%] rounded-2xl rounded-tl-md px-4 py-3 text-[12.5px] text-wb-ink-6">
        出图结果已失效或无法载入
      </div>
    )
  }
  const slots = detailToResultSlots(query.data)
  if (slots.length === 0) return null
  return (
    <ChatResultBlock
      slots={slots}
      done={slots.filter((slot) => slot.url).length}
      total={slots.length}
      onPreview={onPreview}
      onEdit={onEdit}
    />
  )
}
```

Replace each historical render call with:

```tsx
{bubble.jobId && (
  <JobResult
    jobId={bubble.jobId}
    onPreview={setPreviewImage}
    onEdit={selectEditSource}
  />
)}
```

Delete the old inline `ResultBlock` function after both current and historical paths use the extracted component.

Render current results:

```tsx
{state.jobTotal > 0 && (
  <CurrentJobResult
    state={state}
    onPreview={setPreviewImage}
    onEdit={selectEditSource}
  />
)}
```

Render the selected source above the textarea:

```tsx
{selectedEditSource && (
  <div className="mb-2 flex items-center gap-2 rounded-xl border border-wb-brand-soft bg-wb-tint-3 p-2">
    <img
      src={selectedEditSource.url}
      alt=""
      className="size-12 rounded-lg border border-wb-line-1 object-cover"
    />
    <div className="min-w-0 flex-1">
      <p className="text-[12.5px] font-semibold text-wb-brand-deep">
        正在基于此图编辑
      </p>
      <p className="truncate text-[11.5px] text-wb-ink-6">
        输入需要修改的内容，发送后再确认费用
      </p>
    </div>
    <button
      type="button"
      onClick={() => setSelectedEditSource(null)}
      aria-label="取消继续编辑"
      className="grid size-7 place-items-center rounded-full text-wb-ink-5 hover:bg-white"
    >
      <XIcon className="size-4" />
    </button>
  </div>
)}
```

Render the controlled dialog once near the page root:

```tsx
<ChatImagePreviewDialog
  image={previewImage}
  onOpenChange={(open) => {
    if (!open) setPreviewImage(null)
  }}
  onEdit={selectEditSource}
/>
```

- [ ] **Step 6: Run all frontend checks**

Run:

```bash
cd image-web
npm test
npm run lint
npm run typecheck
npm run build
```

Expected: Vitest passes, ESLint reports no errors, TypeScript exits 0, and Vite produces the production bundle.

- [ ] **Step 7: Run all backend checks**

Run:

```bash
cd image-code
uv run pytest -q
uv run ruff check src tests
uv run mypy
```

Expected: all backend tests pass, Ruff reports no issues, and Mypy exits 0.

- [ ] **Step 8: Perform local manual acceptance**

Start the backend:

```bash
cd image-code
uv run uvicorn design_hub.interface.api.asgi:create_production_app --factory --host 127.0.0.1 --port 8000
```

Start the frontend in a second terminal:

```bash
cd image-web
npm run dev -- --host 127.0.0.1 --port 3000
```

Verify at `http://127.0.0.1:3000/chat`:

1. “做一张横版主图” reaches cost confirmation with `4:3`.
2. “做一张横版 16:9 主图” reaches cost confirmation with `16:9`.
3. A completed result opens a full-ratio preview on image click.
4. “继续编辑” selects exactly that result and shows the composer chip.
5. Selection alone sends no request; sending an edit instruction reaches the edit cost confirmation.
6. Confirmed edit returns a new result that can itself be previewed and selected again.
7. Reloading a historical conversation restores result preview and edit actions.

- [ ] **Step 9: Commit the complete Chat interaction**

```bash
git add image-web/src/components/chat/ChatImagePreviewDialog.tsx \
  image-web/src/components/chat/ChatResultBlock.tsx \
  image-web/src/pages/ChatPage.tsx \
  image-web/src/lib/chat.ts \
  image-web/src/lib/chat.test.ts
git commit -m "feat(chat): 支持结果预览与连续编辑" \
  -m "Chat 结果图现在可按原比例打开预览，并通过稳定 image_key 在输入区明确选择下一轮编辑底图；当前与历史结果共享同一交互。"
```

---

## Final Verification

- [ ] Confirm `git status --short` is clean.
- [ ] Confirm the four implementation commits are present after the design and plan commits.
- [ ] Confirm no API key, signed image URL, local `.env`, generated screenshot, or temporary test image is staged.
- [ ] Review the diff against `image-code/docs/superpowers/specs/2026-07-25-chat-landscape-edit-preview-design.md`.
- [ ] Do not push, merge to `dev`, or deploy until the user explicitly requests that action.
