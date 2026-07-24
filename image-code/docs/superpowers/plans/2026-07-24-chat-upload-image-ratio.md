# Chat Upload Image Ratio Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 对话出图在用户未指定比例时自动沿用第一张上传图的受支持比例，识别失败或不支持时使用 `1:1`。

**Architecture:** 在 chat application 层新增纯图片比例识别单元，使用 Pillow 从首图字节读取校正后的宽高并匹配现有四档比例。`ChatOrchestrator` 通过既有 `UploadService` 读取首图，将自动比例作为系统备注注入当前 LLM 用户消息；system prompt 负责声明“文字明确比例优先，否则使用自动比例且不追问”。

**Tech Stack:** Python 3.12、Pillow、FastAPI application layer、pytest、ruff、mypy

## Global Constraints

- 只修改 `image-code/`，不写其他角色目录。
- 支持比例固定为 `1:1`、`3:4`、`9:16`、`16:9`。
- 匹配相对误差上限为 1%；不支持、损坏、读取失败统一回退 `1:1`。
- 多图只读取第一张。
- 不改工作台手动比例、API DTO、底层 size 映射。
- 生产代码必须在对应失败测试之后编写。

---

### Task 1: 图片比例识别单元

**Files:**
- Create: `src/design_hub/application/chat/image_ratio.py`
- Create: `tests/test_chat_image_ratio.py`

**Interfaces:**
- Consumes: `bytes` 图片内容。
- Produces: `detect_supported_ratio(data: bytes) -> str`，只返回四个受支持比例之一。

- [ ] **Step 1: 写四档比例与像素取整误差的失败测试**

```python
from io import BytesIO

from PIL import Image

from design_hub.application.chat.image_ratio import detect_supported_ratio


def _png(width: int, height: int) -> bytes:
    out = BytesIO()
    Image.new("RGB", (width, height)).save(out, format="PNG")
    return out.getvalue()


def test_detects_supported_ratios_and_rounding_error() -> None:
    assert detect_supported_ratio(_png(800, 800)) == "1:1"
    assert detect_supported_ratio(_png(800, 1067)) == "3:4"
    assert detect_supported_ratio(_png(900, 1600)) == "9:16"
    assert detect_supported_ratio(_png(1600, 900)) == "16:9"
```

- [ ] **Step 2: 运行测试并确认因模块不存在而失败**

Run: `uv run pytest tests/test_chat_image_ratio.py -v`

Expected: FAIL，`ModuleNotFoundError: design_hub.application.chat.image_ratio`。

- [ ] **Step 3: 写不支持比例和损坏图片的失败测试**

```python
def test_falls_back_to_square_for_unsupported_or_invalid_image() -> None:
    assert detect_supported_ratio(_png(800, 1000)) == "1:1"
    assert detect_supported_ratio(b"not-an-image") == "1:1"
```

- [ ] **Step 4: 实现最小比例识别器**

```python
from io import BytesIO

from PIL import Image, ImageOps, UnidentifiedImageError

_DEFAULT_RATIO = "1:1"
_MAX_RELATIVE_ERROR = 0.01
_SUPPORTED_RATIOS = {
    "1:1": 1 / 1,
    "3:4": 3 / 4,
    "9:16": 9 / 16,
    "16:9": 16 / 9,
}


def detect_supported_ratio(data: bytes) -> str:
    try:
        with Image.open(BytesIO(data)) as image:
            width, height = ImageOps.exif_transpose(image).size
    except (UnidentifiedImageError, OSError):
        return _DEFAULT_RATIO
    if width <= 0 or height <= 0:
        return _DEFAULT_RATIO
    actual = width / height
    ratio, expected = min(
        _SUPPORTED_RATIOS.items(),
        key=lambda item: abs(actual - item[1]) / item[1],
    )
    relative_error = abs(actual - expected) / expected
    return ratio if relative_error <= _MAX_RELATIVE_ERROR else _DEFAULT_RATIO
```

- [ ] **Step 5: 运行比例测试并确认通过**

Run: `uv run pytest tests/test_chat_image_ratio.py -v`

Expected: 2 passed。

- [ ] **Step 6: 提交比例识别单元**

```bash
git add src/design_hub/application/chat/image_ratio.py tests/test_chat_image_ratio.py
git commit -m "feat(chat): 识别首张上传图比例" -m "使用 Pillow 读取图片尺寸并匹配现有四档比例，允许 1% 像素取整误差；不支持或损坏图片回退 1:1。"
```

### Task 2: 对话上下文注入自动比例

**Files:**
- Modify: `src/design_hub/application/chat/orchestrator.py`
- Modify: `src/design_hub/application/chat/system_prompt.py`
- Modify: `tests/test_chat_harness.py`
- Modify: `tests/test_chat.py`

**Interfaces:**
- Consumes: Task 1 的 `detect_supported_ratio(data: bytes) -> str` 与 `ListingJobLauncher.uploads.load(upload_id)`。
- Produces: `_to_llm_messages(transcript, current_auto_ratio: str | None = None) -> list[ChatMessage]`，以及 `ChatOrchestrator._auto_ratio(upload_ids: list[str]) -> str`。

- [ ] **Step 1: 写系统提示词与上下文备注的失败测试**

```python
def test_build_system_prompt_uses_auto_ratio_without_asking() -> None:
    prompt = build_system_prompt("KB")
    assert "文字明确指定比例时，以文字为准" in prompt
    assert "未指定比例时，使用系统备注中的自动比例" in prompt
    assert "不要追问比例" in prompt
    assert '用户没指定就默认填 "1:1"' not in prompt


def test_current_auto_ratio_is_added_only_to_latest_user_message() -> None:
    transcript = _transcript(3)
    out = _to_llm_messages(transcript, current_auto_ratio="3:4")
    assert "自动比例=3:4" in out[-1].content
    assert all("自动比例=" not in message.content for message in out[:-1])
```

- [ ] **Step 2: 运行 harness 测试并确认因缺少新参数或旧提示词而失败**

Run: `uv run pytest tests/test_chat_harness.py -v`

Expected: FAIL，包含 `_to_llm_messages()` 不接受 `current_auto_ratio` 或新提示词断言失败。

- [ ] **Step 3: 写首图优先与读取失败回退的编排失败测试**

新增一个记录 LLM 输入的 `CapturingTextLLM`，让 `complete()` 保存 `messages` 并返回纯文本；分别：

```python
first = await inf.uploads.save(data=_image_bytes(900, 1600), content_type="image/png", user_id=USER.user_id)
second = await inf.uploads.save(data=_image_bytes(1600, 900), content_type="image/png", user_id=USER.user_id)
await _drain(orch.handle_message(USER, None, "给商品出图", [first, second]))
assert "自动比例=9:16" in llm.messages[-1].content
```

以及：

```python
await _drain(orch.handle_message(USER, None, "给商品出图", ["missing/image.png"]))
assert "自动比例=1:1" in llm.messages[-1].content
```

- [ ] **Step 4: 运行编排测试并确认缺少系统备注而失败**

Run: `uv run pytest tests/test_chat.py -k "auto_ratio" -v`

Expected: FAIL，当前 LLM 用户消息不含 `自动比例=9:16` 或 `自动比例=1:1`。

- [ ] **Step 5: 实现自动比例加载、备注注入和新 prompt 规则**

在 `ChatOrchestrator` 中：

```python
async def _auto_ratio(self, upload_ids: list[str]) -> str:
    if not upload_ids:
        return "1:1"
    try:
        data, _content_type = await self.launcher.uploads.load(upload_ids[0])
    except (ValueError, NotFoundError, OSError):
        return "1:1"
    return detect_supported_ratio(data)
```

在 `handle_message()` 重建上下文前计算：

```python
auto_ratio = await self._auto_ratio(upload_ids)
llm_messages = [
    ChatMessage(role="system", content=self.system_prompt),
    *_to_llm_messages(transcript, current_auto_ratio=auto_ratio),
]
```

`_to_llm_messages()` 只把以下备注加到本轮最后一条 user 消息：

```text
[系统备注] 本轮自动比例=3:4。用户文字明确指定比例时以文字为准；否则使用自动比例，不要追问比例。
```

`system_prompt.py` 同步删除默认 `1:1` 与 ratio 必须追问的旧规则，写入相同优先级。

- [ ] **Step 6: 运行 chat 定向测试并确认通过**

Run: `uv run pytest tests/test_chat_image_ratio.py tests/test_chat_harness.py tests/test_chat.py -v`

Expected: 全部通过。

- [ ] **Step 7: 提交对话集成**

```bash
git add src/design_hub/application/chat/orchestrator.py src/design_hub/application/chat/system_prompt.py tests/test_chat_harness.py tests/test_chat.py
git commit -m "feat(chat): 未指定比例时沿用首张上传图" -m "对话编排读取第一张上传图并注入自动比例；文字明确比例优先，未指定时不再追问，读取失败使用 1:1。"
```

### Task 3: 完整验证与本地验收

**Files:**
- No production file changes.

**Interfaces:**
- Consumes: Tasks 1–2 的完整实现。
- Produces: 可供用户在 `http://localhost:3000/chat` 验收的本地环境。

- [ ] **Step 1: 运行后端完整验证**

Run:

```bash
uv run ruff check .
uv run mypy
uv run pytest
```

Expected: ruff 0 errors，mypy success，pytest 0 failures。

- [ ] **Step 2: 启动本地后端**

Run: `uv run uvicorn design_hub.interface.api.asgi:app --host 127.0.0.1 --port 8000`

Expected: 服务监听 `http://127.0.0.1:8000`。

- [ ] **Step 3: 启动本地前端**

Run: `npm run dev -- --host 127.0.0.1 --port 3000`

Expected: Vite 服务监听 `http://127.0.0.1:3000`。

- [ ] **Step 4: 浏览器验收**

打开 `http://127.0.0.1:3000/chat`，上传一张 `9:16` 图片并输入不含比例的出图要求，确认助手不再追问比例且费用确认参数为 `9:16`；再输入明确 `1:1` 的要求，确认文字比例覆盖自动比例。

- [ ] **Step 5: 等待用户验收**

用户确认本地效果后，才执行 `dev` 合并到 `prod` 及生产部署；验收前不合并、不推送。
