# Unified SSE Image Feedback Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 让所有图片任务在 `image_generated` 到达浏览器后立即回显图片，并用统一契约、幂等槽位归并和有上限的终态校准消除无限转圈。

**Architecture:** 数据库、Outbox 与 Redis Stream 继续只保存稳定 `image_key`；Listing 与 Chat 在 SSE API 边界复用同一展示器生成当前签名 URL。前端用共享纯 reducer 归并所有工作台和 Chat 的成功/失败图片事件，Chat 将图片任务终态与文字流状态拆开，正常链路不轮询，终态或 Chat 断流仅允许一次 job 详情读取。

**Tech Stack:** Python 3.12、FastAPI、Redis Streams、SQLAlchemy async、pytest、React 19、TypeScript 6、TanStack React Query、Vitest。

## Global Constraints

- Python 命令只能通过 `uv run` 执行；不得调用系统 Python 或 `uv pip`。
- 不新增依赖，不修改 `pyproject.toml`、`uv.lock`、`package.json` 或 `package-lock.json`。
- 不新增数据库迁移、Redis Stream、Worker、后台恢复任务或 WebSocket。
- 数据库、Outbox、Redis Stream 只保存 `image_key`，不得持久化签名 URL。
- 正常实时路径零轮询；实时流程每个 job 最多主动读取一次终态详情。
- 不重发一次性 Chat confirm POST；不添加兼容分支、适配器或旧载荷 fallback。
- `image_generated` 必须包含非空 `item_id`、`image_key`、`url`；契约错误 fail-fast，禁止写入空 URL 后继续转圈。
- Listing 与 Chat SSE 都必须返回 `Cache-Control: no-cache` 和 `X-Accel-Buffering: no`。
- 前端成功数从槽位派生；同一 `item_id` 重放必须幂等。
- 每个生产改动先写能够正确失败的测试，再写最小实现。
- 每个任务完成后立即创建独立 commit；提交信息使用英文 `type: description` 并带详细 body。
- 不推送远端，不部署生产。

---

## File Structure

- Create: `image-code/src/design_hub/interface/task_event_presentation.py` — 校验并展示持久任务事件，生成签名 URL，记录 SSE 发出日志。
- Create: `image-code/tests/test_task_event_presentation.py` — 锁定展示契约、输入不可变和 fail-fast 行为。
- Modify: `image-code/src/design_hub/interface/api/routes/listing.py` — Listing SSE 使用共享展示器和统一响应头。
- Modify: `image-code/src/design_hub/interface/api/routes/chat.py` — Chat 嵌套 job 事件使用共享展示器和统一响应头。
- Modify: `image-code/src/design_hub/application/chat/orchestrator.py` — 在 Chat job 事件中保留 Redis event ID，供边界观测使用。
- Modify: `image-code/tests/test_chat_sse.py` — 覆盖嵌套事件展示、心跳与响应头。
- Modify: `image-code/tests/test_chat.py` — 锁定 Chat job 事件的 `redis_id`。
- Modify: `image-web/src/lib/listing.ts` — 定义统一事件、槽位类型、严格解析器、幂等归并和完成数派生。
- Modify: `image-web/src/lib/listing.test.ts` — 覆盖真实载荷、契约错误、乱序与重复事件。
- Modify: `image-web/src/components/listing/ResultGallery.tsx` — 从领域库导入槽位类型，不再拥有状态模型。
- Modify: `image-web/src/api/listing.ts` — 事件 hook 显式报告契约错误；导出一次性详情读取函数。
- Modify: `image-web/src/api/listing.test.ts` — 覆盖解析错误关闭流和一次性读取接口。
- Create: `image-web/src/components/listing/use-terminal-job-reconciliation.ts` — 每 job 最多一次终态详情校准。
- Create: `image-web/src/components/listing/use-terminal-job-reconciliation.test.ts` — 锁定请求上限和合并行为。
- Delete: `image-web/src/components/listing/use-edit-entries.ts` — 由职责准确的新 hook 取代，所有调用方同步迁移。
- Modify: `image-web/src/pages/WorkbenchPage.tsx` — 使用共享槽位 reducer、错误处理和一次终态校准。
- Modify: `image-web/src/pages/CloneWorkbenchPage.tsx` — 同上。
- Modify: `image-web/src/pages/EditWorkbenchPage.tsx` — 同上。
- Modify: `image-web/src/pages/BackgroundWorkbenchPage.tsx` — 同上。
- Modify: `image-web/src/pages/HistoryDetailPage.tsx` — 为 job 查询显式选择交互查询策略。
- Modify: `image-web/src/stores/workbench-store.ts` — 从领域库导入统一槽位类型。
- Modify: `image-web/src/components/chat/ChatResultBlock.tsx` — 从领域库导入统一槽位类型并按派生状态展示。
- Modify: `image-web/src/lib/chat.ts` — Chat 复用槽位 reducer并拆分 `jobStatus` 与 `streaming`。
- Modify: `image-web/src/lib/chat.test.ts` — 覆盖即时回显、终态停止动画和重复事件幂等。
- Modify: `image-web/src/pages/ChatPage.tsx` — 处理 Chat 终态校准、有限断流恢复和独立文字收尾状态。
- Modify: `image-web/src/components/chat/ChatResultBlock.test.ts` — 覆盖任务终态与文字流并行。

---

### Task 1: Present durable task events at the API boundary

**Files:**
- Create: `image-code/src/design_hub/interface/task_event_presentation.py`
- Create: `image-code/tests/test_task_event_presentation.py`

**Interfaces:**
- Consumes: `TaskEventType`, `MediaUrlSigner`。
- Produces: `present_task_event_data(event_type: TaskEventType, data: Mapping[str, object], signer: MediaUrlSigner) -> dict[str, object]`。
- Produces: `log_sse_image_emitted(*, job_id: str, item_id: str, redis_id: str, endpoint_kind: Literal['listing', 'chat']) -> None`。

- [ ] **Step 1: Write failing presenter tests**

创建 `image-code/tests/test_task_event_presentation.py`：

```python
from dataclasses import dataclass

import pytest

from design_hub.domain.enums import TaskEventType
from design_hub.domain.errors import DataInvariantError
from design_hub.interface.task_event_presentation import present_task_event_data
from design_hub.ports.media_url_signer import MediaUrlSigner


@dataclass
class StubSigner(MediaUrlSigner):
    def generated_url(self, key: str) -> str:
        return f"https://img.test/{key}?signed=1"

    def upload_url(self, key: str) -> str:
        return f"https://upload.test/{key}?signed=1"


def test_image_generated_is_presented_without_mutating_durable_data() -> None:
    raw: dict[str, object] = {
        "item_id": "item-1",
        "image_key": "result.png",
        "image_type": "场景",
        "seed": 7,
    }

    presented = present_task_event_data(
        TaskEventType.IMAGE_GENERATED, raw, StubSigner()
    )

    assert presented == {
        **raw,
        "url": "https://img.test/result.png?signed=1",
    }
    assert raw == {
        "item_id": "item-1",
        "image_key": "result.png",
        "image_type": "场景",
        "seed": 7,
    }


@pytest.mark.parametrize("field", ["item_id", "image_key"])
def test_image_generated_requires_non_empty_identity_fields(field: str) -> None:
    data: dict[str, object] = {"item_id": "item-1", "image_key": "result.png"}
    data[field] = ""
    with pytest.raises(DataInvariantError, match=field):
        present_task_event_data(TaskEventType.IMAGE_GENERATED, data, StubSigner())


def test_image_failed_requires_item_id_and_other_events_pass_through() -> None:
    failed = {"item_id": "item-1", "error": "生成失败"}
    assert present_task_event_data(
        TaskEventType.IMAGE_FAILED, failed, StubSigner()
    ) == failed
    assert present_task_event_data(
        TaskEventType.TASK_COMPLETED, {"total_cost": "0.05"}, StubSigner()
    ) == {"total_cost": "0.05"}
```

- [ ] **Step 2: Run the tests and verify RED**

From `image-code`:

```powershell
uv run pytest tests/test_task_event_presentation.py -q
```

Expected: collection fails because `task_event_presentation` does not exist.

- [ ] **Step 3: Implement the strict presenter**

创建 `task_event_presentation.py`，使用 `Mapping` 输入并始终复制输出：

```python
import logging
from collections.abc import Mapping
from typing import Literal

from design_hub.domain.enums import TaskEventType
from design_hub.domain.errors import DataInvariantError
from design_hub.ports.media_url_signer import MediaUrlSigner

logger = logging.getLogger(__name__)


def _required_text(data: Mapping[str, object], field: str) -> str:
    value = data.get(field)
    if not isinstance(value, str) or not value:
        raise DataInvariantError(f"task event {field} must be a non-empty string")
    return value


def present_task_event_data(
    event_type: TaskEventType,
    data: Mapping[str, object],
    signer: MediaUrlSigner,
) -> dict[str, object]:
    presented = dict(data)
    if event_type == TaskEventType.IMAGE_GENERATED:
        _required_text(data, "item_id")
        image_key = _required_text(data, "image_key")
        presented["url"] = signer.generated_url(image_key)
    elif event_type == TaskEventType.IMAGE_FAILED:
        _required_text(data, "item_id")
    return presented


def log_sse_image_emitted(
    *,
    job_id: str,
    item_id: str,
    redis_id: str,
    endpoint_kind: Literal["listing", "chat"],
) -> None:
    logger.info(
        "generation_sse_image_emitted",
        extra={
            "chain": "image_generation",
            "action": "发送图片实时事件",
            "status": "emitted",
            "job_id": job_id,
            "item_id": item_id,
            "redis_id": redis_id,
            "endpoint_kind": endpoint_kind,
        },
    )
```

- [ ] **Step 4: Run presenter tests and static checks**

```powershell
uv run pytest tests/test_task_event_presentation.py -q
uv run ruff check src/design_hub/interface/task_event_presentation.py tests/test_task_event_presentation.py
uv run mypy src
```

Expected: all pass.

- [ ] **Step 5: Commit the presenter unit**

```powershell
git add image-code/src/design_hub/interface/task_event_presentation.py image-code/tests/test_task_event_presentation.py
git commit -m "feat: present image task events for SSE" -m "Validate durable image events and add signed display URLs only at the API presentation boundary. Keep stored event payloads immutable and provide bounded structured emission logging without persisting signed URLs."
```

---

### Task 2: Wire Listing and Chat through the shared SSE contract

**Files:**
- Modify: `image-code/src/design_hub/interface/api/routes/listing.py`
- Modify: `image-code/src/design_hub/interface/api/routes/chat.py`
- Modify: `image-code/src/design_hub/application/chat/orchestrator.py`
- Modify: `image-code/tests/test_chat_sse.py`
- Modify: `image-code/tests/test_chat.py`
- Modify: `image-code/tests/test_task_event_presentation.py`

**Interfaces:**
- Consumes: `present_task_event_data(...)` and `log_sse_image_emitted(...)` from Task 1.
- Produces: Listing `image_generated` SSE data `{item_id, image_key, url, ...}`。
- Produces: Chat `job_event.data` with the identical task-event payload and outer `redis_id`。
- Produces: `SSE_RESPONSE_HEADERS = {'Cache-Control': 'no-cache', 'X-Accel-Buffering': 'no'}` shared from `task_event_presentation.py`。

- [ ] **Step 1: Add failing serialization and header tests**

扩展 `test_task_event_presentation.py`，直接构造 `ReplayableEvent` 并测试 Listing `_sse`；扩展 `test_chat_sse.py` 测试 Chat 嵌套载荷：

```python
def test_listing_sse_presents_image_key_and_url() -> None:
    delivery = ReplayableEvent(
        redis_id="10-0",
        event=TaskEvent(
            job_id="job-1",
            type=TaskEventType.IMAGE_GENERATED,
            data={"item_id": "item-1", "image_key": "result.png"},
        ),
    )
    payload = listing_sse(delivery, StubSigner())
    assert "id: 10-0" in payload
    assert '"image_key": "result.png"' in payload
    assert '"url": "https://img.test/result.png?signed=1"' in payload


def test_chat_stream_presents_nested_job_event() -> None:
    async def source() -> AsyncIterator[ChatEvent]:
        yield ChatEvent("job_event", {
            "job_id": "job-1",
            "redis_id": "10-0",
            "type": "image_generated",
            "data": {"item_id": "item-1", "image_key": "result.png"},
        })

    stream = _stream_chat_events(source(), StubSigner())
    payload = asyncio.run(anext(stream))
    assert '"image_key": "result.png"' in payload
    assert '"url": "https://img.test/result.png?signed=1"' in payload
```

在同一测试文件断言：

```python
assert SSE_RESPONSE_HEADERS == {
    "Cache-Control": "no-cache",
    "X-Accel-Buffering": "no",
}
```

- [ ] **Step 2: Run focused tests and verify RED**

```powershell
uv run pytest tests/test_task_event_presentation.py tests/test_chat_sse.py -q
```

Expected: FAIL because serializers do not accept a signer, Chat does not present nested data, and the shared header constant is absent.

- [ ] **Step 3: Preserve Redis IDs in Chat job events**

在 `ChatOrchestrator.handle_confirm` 转发 job 事件时加入：

```python
yield ChatEvent(
    "job_event",
    {
        "job_id": job_id,
        "redis_id": delivery.redis_id,
        "type": event.type.value,
        "data": event.data,
    },
)
```

更新 `test_confirm_launches_job_and_forwards_job_events`，断言每条 `job_event` 的 `redis_id` 为非空字符串。不要改变公开任务事件名称。

- [ ] **Step 4: Present and log Listing events**

将 Listing `_sse` 改为接收 signer。仅当 `IMAGE_GENERATED` 成功展示后记录发送日志：

```python
def _sse(delivery: ReplayableEvent, signer: MediaUrlSigner) -> str:
    event = delivery.event
    data = present_task_event_data(event.type, event.data, signer)
    if event.type == TaskEventType.IMAGE_GENERATED:
        log_sse_image_emitted(
            job_id=event.job_id,
            item_id=cast(str, data["item_id"]),
            redis_id=delivery.redis_id,
            endpoint_kind="listing",
        )
    return (
        f"id: {delivery.redis_id}\n"
        f"event: {event.type.value}\n"
        f"data: {json.dumps(data, ensure_ascii=False)}\n\n"
    )
```

在 `listing_events` 取得 `request.app.state.media_signer`，传给 `_sse`，并用共享 `SSE_RESPONSE_HEADERS` 构造响应。

- [ ] **Step 5: Present and log nested Chat events**

让 `_stream_chat_events` 接收 `MediaUrlSigner`。序列化 `job_event` 前复制外层 data，解析 `TaskEventType`，调用共享展示器替换内层 `data`。成功图片事件调用 `log_sse_image_emitted(..., endpoint_kind='chat')`。非 job 事件原样序列化。

`chat_messages` 和 `chat_confirm` 均从 `request.app.state.media_signer` 取得 signer，并设置共享 SSE 响应头。不要把 signer 注入 Chat Orchestrator。

- [ ] **Step 6: Update the existing heartbeat test without weakening it**

把现有调用改为：

```python
stream = _stream_chat_events(
    source(), StubSigner(), heartbeat_seconds=0.01
)
```

继续断言心跳不会取消上游迭代器，随后仍收到 `assistant_end`。

- [ ] **Step 7: Run backend route and chat gates**

```powershell
uv run pytest tests/test_task_event_presentation.py tests/test_chat_sse.py tests/test_chat.py -q
uv run ruff check src tests/test_task_event_presentation.py tests/test_chat_sse.py tests/test_chat.py
uv run mypy src
```

Expected: all pass.

- [ ] **Step 8: Commit the unified backend boundary**

```powershell
git add image-code/src/design_hub/interface/task_event_presentation.py image-code/src/design_hub/interface/api/routes/listing.py image-code/src/design_hub/interface/api/routes/chat.py image-code/src/design_hub/application/chat/orchestrator.py image-code/tests/test_task_event_presentation.py image-code/tests/test_chat_sse.py image-code/tests/test_chat.py
git commit -m "fix: unify image events across SSE endpoints" -m "Present the same signed image payload through Listing and Chat, preserve Redis event IDs for observability, and disable proxy buffering on both streaming endpoints. Durable Redis and database events remain key-only."
```

---

### Task 3: Build the strict frontend event and slot reducer

**Files:**
- Modify: `image-web/src/lib/listing.ts`
- Modify: `image-web/src/lib/listing.test.ts`
- Modify: `image-web/src/components/listing/ResultGallery.tsx`
- Modify: `image-web/src/stores/workbench-store.ts`
- Modify: `image-web/src/components/chat/ChatResultBlock.tsx`
- Modify: `image-web/src/lib/chat.ts`
- Modify: `image-web/src/components/listing/use-edit-entries.ts`

**Interfaces:**
- Produces: `ResultSlot` in `@/lib/listing` with `itemId?: string`。
- Produces: strict `ListingEvent` image variants with `itemId` and success `imageKey/url`。
- Produces: `applyListingEventToSlots(slots, event) -> ResultSlot[]`。
- Produces: `settledSlotCount(slots: readonly ResultSlot[]) -> number`。

- [ ] **Step 1: Replace parser fixtures with the real contract and verify RED**

在 `listing.test.ts` 的 `parseListingEvent` suite 使用：

```typescript
it('parses the complete image presentation contract', () => {
  expect(parseListingEvent('image_generated', JSON.stringify({
    item_id: 'item-1',
    image_key: 'result.png',
    url: 'https://img.test/result.png?signed=1',
    seed: 7,
    image_type: '卖点',
  }))).toEqual({
    kind: 'image',
    itemId: 'item-1',
    imageKey: 'result.png',
    url: 'https://img.test/result.png?signed=1',
    seed: 7,
    imageType: '卖点',
  })
})

it.each(['item_id', 'image_key', 'url'])('rejects image events with empty %s', (field) => {
  const data = {
    item_id: 'item-1', image_key: 'result.png', url: 'https://img.test/result.png',
  }
  data[field as keyof typeof data] = ''
  expect(() => parseListingEvent('image_generated', JSON.stringify(data)))
    .toThrow(`${field} must be a non-empty string`)
})

it('parses image_failed with stable item identity', () => {
  expect(parseListingEvent('image_failed', JSON.stringify({
    item_id: 'item-2', image_type: '场景', error: '生成失败',
  }))).toEqual({
    kind: 'image_failed', itemId: 'item-2', imageType: '场景', error: '生成失败',
  })
})
```

运行：

```powershell
npm test -- src/lib/listing.test.ts
```

Expected: FAIL because the parser drops `item_id/image_key` and accepts empty URL.

- [ ] **Step 2: Define the strict contract and relocate ResultSlot**

在 `lib/listing.ts` 定义 `ResultSlot`，取代 `ResultSlotLike` 和组件内的 `ResultSlot`：

```typescript
export interface ResultSlot {
  url: string | null
  itemId?: string
  imageType?: string
  error?: string
  imageKey?: string
  unavailable?: boolean
}
```

用私有 `requiredEventText(data, field)` 校验必填字符串。更新事件 union 和解析器。`ResultGallery.tsx`、store、Chat、校准 hook 全部从 `@/lib/listing` 导入该类型；不保留组件 re-export 或旧类型别名。

- [ ] **Step 3: Write failing reducer tests**

在 `listing.test.ts` 新增：

```typescript
describe('applyListingEventToSlots', () => {
  const slots: ResultSlot[] = [
    { url: null, imageType: '白底' },
    { url: null, imageType: '场景' },
    { url: null, imageType: '场景' },
  ]

  it('fills by image type and derives settled count', () => {
    const one = applyListingEventToSlots(slots, {
      kind: 'image', itemId: 'i1', imageKey: 'k1', url: 'https://x/1', imageType: '场景',
    })
    const two = applyListingEventToSlots(one, {
      kind: 'image_failed', itemId: 'i2', imageType: '白底', error: '失败',
    })
    expect(two[0]).toMatchObject({ itemId: 'i2', error: '失败' })
    expect(two[1]).toMatchObject({ itemId: 'i1', imageKey: 'k1', url: 'https://x/1' })
    expect(settledSlotCount(two)).toBe(2)
  })

  it('replays the same item idempotently', () => {
    const event = {
      kind: 'image', itemId: 'i1', imageKey: 'k1', url: 'https://x/1', imageType: '场景',
    } as const
    const once = applyListingEventToSlots(slots, event)
    const replayed = applyListingEventToSlots(once, { ...event, url: 'https://x/1?fresh=1' })
    expect(replayed.filter((slot) => slot.itemId === 'i1')).toHaveLength(1)
    expect(replayed[1].url).toBe('https://x/1?fresh=1')
    expect(settledSlotCount(replayed)).toBe(1)
  })

  it('fails when no planned slot can accept a new item', () => {
    const full = [{ url: 'https://x/1', itemId: 'i1' }]
    expect(() => applyListingEventToSlots(full, {
      kind: 'image', itemId: 'i2', imageKey: 'k2', url: 'https://x/2',
    })).toThrow('no result slot available for item i2')
  })
})
```

- [ ] **Step 4: Run reducer tests and verify RED**

```powershell
npm test -- src/lib/listing.test.ts
```

Expected: FAIL because the shared reducer and settled counter do not exist.

- [ ] **Step 5: Implement the pure reducer and derived count**

Use the exact public signatures:

```typescript
export type SettlingListingEvent = Extract<
  ListingEvent,
  { kind: 'image' | 'image_failed' }
>

export function applyListingEventToSlots(
  slots: readonly ResultSlot[],
  event: SettlingListingEvent,
): ResultSlot[]

export function settledSlotCount(slots: readonly ResultSlot[]): number
```

First locate an existing `itemId`; otherwise locate the first unsettled compatible image type. Return a copied array and copied slot. Throw when no slot exists. A settled slot is one with `url`, `error`, or `unavailable`.

- [ ] **Step 6: Update detail merge types and all type imports**

Change `mergeSlotsWithDetail` and `detailToResultSlots` to return/use `ResultSlot`. Update every import found by:

```powershell
rg -n "components/listing/ResultGallery.*ResultSlot|ResultSlotLike" image-web/src
```

Expected after edits: no matches. Do not change page event logic yet; only make the type move compile.

- [ ] **Step 7: Run frontend domain gates**

```powershell
npm test -- src/lib/listing.test.ts src/lib/chat.test.ts src/components/chat/ChatResultBlock.test.ts
npm run typecheck
```

Expected: all pass.

- [ ] **Step 8: Commit the frontend domain unit**

```powershell
git add image-web/src/lib/listing.ts image-web/src/lib/listing.test.ts image-web/src/components/listing/ResultGallery.tsx image-web/src/stores/workbench-store.ts image-web/src/components/chat/ChatResultBlock.tsx image-web/src/lib/chat.ts image-web/src/components/listing/use-edit-entries.ts
git commit -m "refactor: unify image event slot state" -m "Move result-slot state into the listing domain, parse the complete SSE image contract, and merge success or failure events idempotently by item ID. All existing consumers now depend on one strict event model."
```

---

### Task 4: Adapt every workbench and bound terminal reconciliation

**Files:**
- Modify: `image-web/src/api/listing.ts`
- Modify: `image-web/src/api/listing.test.ts`
- Create: `image-web/src/components/listing/use-terminal-job-reconciliation.ts`
- Create: `image-web/src/components/listing/use-terminal-job-reconciliation.test.ts`
- Delete: `image-web/src/components/listing/use-edit-entries.ts`
- Modify: `image-web/src/pages/WorkbenchPage.tsx`
- Modify: `image-web/src/pages/CloneWorkbenchPage.tsx`
- Modify: `image-web/src/pages/EditWorkbenchPage.tsx`
- Modify: `image-web/src/pages/BackgroundWorkbenchPage.tsx`

**Interfaces:**
- Consumes: `applyListingEventToSlots` and `settledSlotCount` from Task 3.
- Produces: `fetchListingJob(jobId: string): Promise<ListingJobDetail>`。
- Produces: `useListingJob(jobId, policy: 'interactive' | 'single')`；`single` 禁用自动 retry、窗口聚焦和网络恢复 refetch。
- Produces: `useTerminalJobReconciliation(applyDetail)` returning `{ reconcile(jobId): Promise<void>, reset(): void }`，每个 job 最多一次网络请求。
- Produces: `useListingEvents(jobId, { onEvent, onContractError })`；传输错误继续由原生 EventSource 重连。

- [ ] **Step 1: Write failing one-shot reconciliation tests**

创建 hook 的测试，以导出的纯控制器避免依赖计时器：

```typescript
it('fetches and merges each terminal job at most once', async () => {
  const fetchJob = vi.fn().mockResolvedValue(detail({
    images: [okImage('k1', '场景')],
  }))
  const applyDetail = vi.fn()
  const reconciler = createTerminalJobReconciler(fetchJob, applyDetail)

  await reconciler.reconcile('job-1')
  await reconciler.reconcile('job-1')

  expect(fetchJob).toHaveBeenCalledTimes(1)
  expect(applyDetail).toHaveBeenCalledTimes(1)
})

it('does not retry a failed reconciliation implicitly', async () => {
  const fetchJob = vi.fn().mockRejectedValue(new Error('network'))
  const reconciler = createTerminalJobReconciler(fetchJob, vi.fn())
  await expect(reconciler.reconcile('job-1')).rejects.toThrow('network')
  await reconciler.reconcile('job-1')
  expect(fetchJob).toHaveBeenCalledTimes(1)
})
```

- [ ] **Step 2: Run the reconciliation test and verify RED**

```powershell
npm test -- src/components/listing/use-terminal-job-reconciliation.test.ts
```

Expected: FAIL because the module does not exist.

- [ ] **Step 3: Export a direct job-detail reader and implement the one-shot controller**

在 `api/listing.ts` 导出：

```typescript
export const fetchListingJob = (jobId: string) =>
  authGet<ListingJobDetail>(`/listing/jobs/${jobId}`)
```

`createTerminalJobReconciler` 在发请求前把 job ID 写入 `Set`，因此成功或失败都不会隐式重试。React hook 用 `useRef` 保存控制器，并把成功详情交给调用方提供的 `applyDetail(detail)`；工作台调用方在该回调中使用 `setSlots(prev => mergeSlotsWithDetail(prev, detail.images))`，Chat 调用方则在同一个回调中更新 `ChatState`。`reset()` 只为开始新任务清理本地已处理 ID，不触发请求。

同时把 `useListingJob` 改为要求显式查询策略：

```typescript
export type ListingJobQueryPolicy = 'interactive' | 'single'

export function useListingJob(
  jobId: string | undefined,
  policy: ListingJobQueryPolicy,
) {
  const single = policy === 'single'
  return useQuery({
    queryKey: ['listing', 'job', jobId],
    queryFn: () => fetchListingJob(jobId!),
    enabled: Boolean(jobId),
    retry: single ? false : undefined,
    refetchOnWindowFocus: single ? false : undefined,
    refetchOnReconnect: single ? false : undefined,
  })
}
```

更新所有调用方，不保留旧签名：实时终态校准使用 `single`；历史详情和用户主动查看使用 `interactive`。

- [ ] **Step 4: Write failing EventSource contract-error tests**

在 `api/listing.test.ts` 使用假的 EventSource，发送一个缺 `url` 的 `image_generated`，断言：

```typescript
expect(onContractError).toHaveBeenCalledWith(
  expect.objectContaining({ message: expect.stringContaining('url must be a non-empty string') }),
)
expect(eventSource.close).toHaveBeenCalledTimes(1)
```

同时触发原生 `error` 事件，断言 hook 不调用 `close()`，从而保留浏览器自动重连。

- [ ] **Step 5: Change `useListingEvents` to explicit handlers**

使用：

```typescript
interface ListingEventHandlers {
  onEvent: (event: ListingEvent) => void
  onContractError: (error: Error) => void
}

export function useListingEvents(
  jobId: string | null,
  handlers: ListingEventHandlers,
): void
```

只捕获解析器或 `onEvent` 抛出的非 I/O 契约错误：关闭 EventSource 并调用 `onContractError`。不要覆盖 `es.onerror`，让浏览器继续执行原生重连与 `Last-Event-ID`。

- [ ] **Step 6: Adapt all four workbench pages**

复刻、编辑和换背景页的成功/失败分支统一为：

```typescript
if (event.kind === 'image' || event.kind === 'image_failed') {
  setSlots((current) => applyListingEventToSlots(current, event))
} else if (event.kind === 'completed' || event.kind === 'failed') {
  if (jobId) void reconciliation.reconcile(jobId).catch(showReconcileError)
  stopGenerating()
}
```

各页保留自己的业务失败 toast 和任务 ID 清理。`onContractError` 必须停止当前页面动画并显示“图片事件格式异常”，不能继续留在生成态。完成数统一在 render 前由 `settledSlotCount(slots)` 计算；删除 `setDone(d => d + 1)` 状态。

普通 Workbench 继续用现有 `detail` 查询完成终态接管，并将该调用改为 `useListingJob(..., 'single')`；它不得再调用 reconciliation hook，否则会产生双请求。复刻、编辑、换背景删除 `useEditEntries` 调用并改用新 reconciliation hook。`HistoryDetailPage` 使用 `interactive`；Chat 现有历史 `JobResult` 暂时使用 `interactive`，Task 5 再处理当前任务的 terminal reconciliation。

- [ ] **Step 7: Run workbench tests and typecheck**

```powershell
npm test -- src/lib/listing.test.ts src/api/listing.test.ts src/components/listing/use-terminal-job-reconciliation.test.ts
npm run typecheck
```

Expected: all pass.

- [ ] **Step 8: Run all frontend tests before commit**

```powershell
npm test
npm run lint
```

Expected: all pass without new warnings.

- [ ] **Step 9: Commit the unified workbench path**

```powershell
git add image-web/src/api/listing.ts image-web/src/api/listing.test.ts image-web/src/components/listing/use-terminal-job-reconciliation.ts image-web/src/components/listing/use-terminal-job-reconciliation.test.ts image-web/src/components/listing/use-edit-entries.ts image-web/src/pages/WorkbenchPage.tsx image-web/src/pages/CloneWorkbenchPage.tsx image-web/src/pages/EditWorkbenchPage.tsx image-web/src/pages/BackgroundWorkbenchPage.tsx image-web/src/pages/HistoryDetailPage.tsx image-web/src/pages/ChatPage.tsx
git commit -m "fix: render workbench images from SSE" -m "Route every image workbench through the shared idempotent slot reducer, stop spinners on explicit terminal or contract states, and reconcile each terminal job with at most one detail request. Native EventSource replay remains the only transport recovery path."
```

---

### Task 5: Separate Chat image terminal state from text streaming

**Files:**
- Modify: `image-web/src/lib/chat.ts`
- Modify: `image-web/src/lib/chat.test.ts`
- Modify: `image-web/src/pages/ChatPage.tsx`
- Modify: `image-web/src/components/chat/ChatResultBlock.tsx`
- Modify: `image-web/src/components/chat/ChatResultBlock.test.ts`
- Modify: `image-web/src/api/chat.ts`
- Modify: `image-web/src/api/chat.test.ts`

**Interfaces:**
- Consumes: shared slot reducer and terminal reconciler from Tasks 3–4.
- Produces: `ChatJobStatus = 'idle' | 'generating' | 'completed' | 'failed' | 'interrupted'`。
- Produces: `ChatState.jobStatus` independent from `ChatState.streaming`。
- Produces: `streamSSE` failure preserves the last applied `job_started` state; Chat performs one detail read and never resends confirm.

- [ ] **Step 1: Write failing Chat reducer tests**

替换旧的 Chat 图片 fixture，使用完整事件：

```typescript
it('shows an image immediately and stops image generation before assistant_end', () => {
  let state = feed(initialChatState(), [
    { kind: 'job_started', jobId: 'j1', tool: 'generate', count: 1 },
    {
      kind: 'job', jobId: 'j1',
      inner: {
        kind: 'image', itemId: 'i1', imageKey: 'k1',
        url: 'https://img.test/k1', imageType: '场景',
      },
      imageType: '场景',
    },
    { kind: 'job', jobId: 'j1', inner: { kind: 'completed' } },
  ])

  expect(state.slots[0]).toMatchObject({ imageKey: 'k1', url: 'https://img.test/k1' })
  expect(state.jobStatus).toBe('completed')
  expect(state.streaming).toBe(true)

  state = applyChatEvent(state, { kind: 'assistant_end', status: 'complete' })
  expect(state.streaming).toBe(false)
})

it('replays a job image without changing settled count', () => {
  const event = completeJobImageEvent('j1', 'i1', 'k1')
  const once = applyChatEvent(startedChatJob('j1', 1), event)
  const twice = applyChatEvent(once, event)
  expect(settledSlotCount(twice.slots)).toBe(1)
})

it('marks task_failed as terminal without waiting for assistant_end', () => {
  const state = applyChatEvent(startedChatJob('j1', 1), {
    kind: 'job', jobId: 'j1', inner: { kind: 'failed', error: '出图失败' },
  })
  expect(state.jobStatus).toBe('failed')
  expect(state.streaming).toBe(true)
})
```

- [ ] **Step 2: Run Chat reducer tests and verify RED**

```powershell
npm test -- src/lib/chat.test.ts
```

Expected: FAIL because current Chat ignores task terminal events and couples image fallback to `streaming`.

- [ ] **Step 3: Implement independent Chat job state**

在 `initialChatState` 设置 `jobStatus: 'idle'`。`job_started` 设为 `generating` 并预铺槽位；成功/失败图片调用 `applyListingEventToSlots`；`completed/failed` 只更新 `jobStatus`。`assistant_end` 只更新 `streaming` 和 assistant bubble。

移除 `jobDone` 累加，展示时调用 `settledSlotCount(state.slots)`。`CurrentJobResult` 不再用 `!state.streaming` 决定何时读取详情；改由 `jobStatus` 终态触发 Task 4 的一次性 reconciliation。

- [ ] **Step 4: Write a failing Chat transport interruption test**

在 `chat.test.ts` 为 `streamSSE` 或导出的帧消费器构造：先发送 `job_started`，随后 reader 抛出网络错误。断言调用方能区分已经存在 `activeJobId='j1'`。在 `ChatPage` 的纯状态辅助函数测试：

```typescript
expect(interruptChatJob(startedChatJob('j1', 2))).toMatchObject({
  activeJobId: 'j1',
  jobStatus: 'interrupted',
  streaming: false,
})
```

没有 job ID 时 `interruptChatJob(initialChatState())` 仅结束文字流，不伪造任务。

- [ ] **Step 5: Implement bounded Chat interruption recovery**

先把 SSE 事件提交收敛为同步更新 `stateRef` 的单一路径，避免 React 批处理导致 catch 读取到 `job_started` 之前的旧快照：

```typescript
function commitChatEvent(event: ChatEvent): void {
  const next = applyChatEvent(stateRef.current, event)
  stateRef.current = next
  setState(next)
}
```

普通事件和模型不可用分支都必须显式维护 `stateRef`；不得继续让 SSE 事件只调用异步 `setState(prev => ...)`。补测试锁定 `job_started` 后立即发生 reader 错误时仍能取得 job ID。

在 `confirmChat` catch 中：

- 若 `stateRef.current.activeJobId` 为空，保持现有请求失败处理。
- 若存在 job ID，调用 `interruptChatJob`，显示“连接已中断，任务仍在后台执行”，并调用一次 `fetchListingJob(jobId)`。
- 详情若为终态则用 `detailToResultSlots` 替换槽位并设置相应 `jobStatus`。
- 详情若仍为生成中，保持 `interrupted` 文案，不设置计时器、不轮询、不重发 confirm。
- 一次读取失败只显示错误；不 catch-and-ignore，不自动重试。

正常 `task_completed/task_failed` 使用 terminal reconciliation；断流恢复与终态校准共享同一个 per-job 请求闸，确保两条路径合计最多一次主动详情 GET。

- [ ] **Step 6: Make ChatResultBlock render explicit terminal state**

给组件增加 `status: ChatJobStatus | 'idle'` 或等价的展示输入。`generating` 才允许等待槽转圈；`failed`、`completed`、`interrupted` 的未结算槽显示明确终态文案，不继续动画。文字 `streaming` 不传入该组件。

- [ ] **Step 7: Run focused Chat tests**

```powershell
npm test -- src/lib/chat.test.ts src/api/chat.test.ts src/components/chat/ChatResultBlock.test.ts
npm run typecheck
```

Expected: all pass.

- [ ] **Step 8: Run all frontend quality gates**

```powershell
npm test
npm run typecheck
npm run lint
npm run build
```

Expected: all pass without new warnings.

- [ ] **Step 9: Commit the Chat state unit**

```powershell
git add image-web/src/lib/chat.ts image-web/src/lib/chat.test.ts image-web/src/pages/ChatPage.tsx image-web/src/components/chat/ChatResultBlock.tsx image-web/src/components/chat/ChatResultBlock.test.ts image-web/src/api/chat.ts image-web/src/api/chat.test.ts
git commit -m "fix: stop chat image spinners at task terminal" -m "Render signed image events immediately, separate image task status from assistant text streaming, and bound Chat disconnect recovery to one job-detail read without polling or replaying confirmation requests."
```

---

### Task 6: Verify the full chain and close the implementation scope

**Files:**
- Verify: `image-code/tests/integration/test_stage_a_task_chain.py`
- Verify: `image-code/scripts/load_test_stage_a.py`
- Verify: all files changed in Tasks 1–5.
- Do not modify dependency manifests, migrations, generated OpenAPI files, unrelated PRDs or deployment configuration.

**Interfaces:**
- Consumes: shared backend SSE presenter, frontend slot reducer, bounded reconciliation and Chat job status.
- Produces: test and manual evidence for Worker → DB/Outbox → Redis Stream → SSE → frontend state.

- [ ] **Step 1: Add or update the integration assertion for event order and payload**

在现有 Stage A task-chain integration test 的事件断言中验证：

```python
image_index = types.index(TaskEventType.IMAGE_GENERATED)
terminal_index = types.index(TaskEventType.TASK_COMPLETED)
assert image_index < terminal_index

image_event = job_events[image_index].event
assert image_event.data["item_id"]
assert image_event.data["image_key"]
assert "url" not in image_event.data
```

该断言锁定 Redis 持久事件仍不包含 URL。API presenter 的 URL 已由 Task 2 路由测试覆盖。

- [ ] **Step 2: Run full backend gates**

From `image-code`:

```powershell
uv run pytest -q
uv run ruff check src tests
uv run mypy src
```

Expected: all pass. Existing known failures must be reported and proven pre-existing before continuing; do not weaken tests.

- [ ] **Step 3: Run full frontend gates from a clean process**

From `image-web`:

```powershell
npm test
npm run typecheck
npm run lint
npm run build
```

Expected: all pass.

- [ ] **Step 4: Run a local Redis end-to-end smoke**

Use the existing local API, Worker and Redis process. Submit one mock or non-billable test job through Listing and one through Chat confirm. Capture the SSE frames and assert for both:

```text
image_generated contains non-empty item_id, image_key and url
image_generated arrives before task_completed
Chat may continue assistant_delta after task_completed
```

Do not run a paid provider request without explicit user authorization. If the local environment cannot provide a non-billable image job, report the smoke as blocked and rely on automated route/integration coverage.

- [ ] **Step 5: Verify Nginx buffering headers without deployment**

For both streaming endpoints, inspect response headers through the configured local reverse proxy or test client:

```text
Cache-Control: no-cache
X-Accel-Buffering: no
```

If no local Nginx is available, record route-test evidence and leave production proxy verification as a deployment acceptance item; do not alter ops configuration speculatively.

- [ ] **Step 6: Inspect scope and commit the integration assertion if changed**

```powershell
git diff --check
git status --short
git diff --name-only HEAD~5
```

Expected: only files enumerated by this plan plus the Stage A integration assertion are changed. If the integration test changed, commit it:

```powershell
git add image-code/tests/integration/test_stage_a_task_chain.py
git commit -m "test: verify realtime image event ordering" -m "Lock the durable event chain to emit keyed image completion before task terminal while keeping signed display URLs out of Redis payloads."
```

Do not create an empty verification commit.

- [ ] **Step 7: Final completion report**

Report:

- implementation commit hashes from Tasks 1–5 and optional Task 6 test commit;
- exact backend and frontend commands with pass counts;
- Listing and Chat SSE payload evidence;
- whether local Nginx evidence was available;
- confirmation that no polling, migration, dependency, remote or deployment changes were introduced;
- any deployment-only acceptance item still outstanding.

Do not claim completion if any required automated gate is failing or if the worktree is dirty from this scope.
