# Chat Generation Recovery Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 让仍在生图的历史会话在刷新或重新进入后恢复完整占位槽、逐张结果和旋转动画，并在任务终态自动停止刷新。

**Architecture:** 在 `job_started` 前用现有 `chat_message.job_id` 持久化任务与会话的关联，终态更新同一条消息。前端把当前任务和历史任务统一为 `jobId -> listing job detail -> slots -> ChatResultBlock`，SSE 只负责即时通知，数据库任务详情负责可恢复状态。

**Tech Stack:** Python 3.12、FastAPI application service、SQLAlchemy async、pytest、React 19、TypeScript 6、TanStack React Query、Vitest。

## Global Constraints

- 不新增或修改数据库列，不创建 Alembic migration。
- 不改变公开 chat/listing HTTP API 和现有 SSE 事件名称或载荷。
- `confirm_token` 继续只存在于内存过程态；取消确认不创建任务消息。
- 会话删除继续只删除会话转录，不取消或删除已经提交的 `listing_job`。
- 当前实时任务和历史恢复必须使用同一个任务结果组件和同一个 React Query key。
- 只有 `status='生成中'` 的当前可见任务轮询；终态或组件卸载后停止。
- 不为非 I/O 逻辑增加重试、fallback 或静默错误处理。
- Python 命令只能通过 `uv run` 执行。
- 每个生产代码改动必须先有能够正确失败的测试。

---

## File Structure

- Modify: `image-code/src/design_hub/ports/chat_repository.py` — 定义任务消息创建与原位更新接口。
- Modify: `image-code/src/design_hub/infrastructure/db/chat_repo.py` — 返回消息 ID，并按 session/message ID 更新同一条 assistant 消息。
- Modify: `image-code/src/design_hub/application/chat/orchestrator.py` — 在 `job_started` 前建立持久化关联，终态更新原消息。
- Modify: `image-code/tests/test_chat.py` — 锁定持久化顺序、单消息更新、取消与失败行为。
- Modify: `image-web/src/lib/listing.ts` — 从生成中详情构建完整槽位，并计算已处理槽位数。
- Modify: `image-web/src/lib/listing.test.ts` — 覆盖零结果、部分结果、失败槽和终态回归。
- Modify: `image-web/src/api/listing.ts` — 统一 job query key，按状态控制轮询。
- Modify: `image-web/src/api/listing.test.ts` — 覆盖生成中轮询与终态停止策略。
- Create: `image-web/src/components/chat/ChatJobResult.tsx` — 当前与历史共用的任务查询和结果展示组件。
- Create: `image-web/src/components/chat/ChatJobResult.test.ts` — 覆盖生成中、终态、加载和错误展示。
- Modify: `image-web/src/pages/ChatPage.tsx` — 使用统一结果组件，并让 SSE 事件刷新同一任务缓存。
- Modify: `image-web/src/lib/chat.ts` — 移除 SSE 槽位副本，并把 `job_started` 的 ID 挂到对应 assistant 气泡。
- Modify: `image-web/src/lib/chat.test.ts` — 锁定 reducer 只记录 job ID、历史 job ID 仍可恢复。

---

### Task 1: Persist the job anchor before `job_started`

**Files:**
- Modify: `image-code/tests/test_chat.py`
- Modify: `image-code/src/design_hub/ports/chat_repository.py`
- Modify: `image-code/src/design_hub/infrastructure/db/chat_repo.py`
- Modify: `image-code/src/design_hub/application/chat/orchestrator.py`

**Interfaces:**
- Produces: `append_message(...) -> str`，返回新建 `chat_message.id`。
- Produces: `update_assistant_message(*, session_id: str, message_id: str, content: str) -> None`。
- Preserves: 所有公开 SSE 事件与 HTTP schema。

- [ ] **Step 1: Add a failing repository test for message identity and in-place update**

在 `image-code/tests/test_chat.py` 的持久化测试区加入：

```python
def test_chat_repository_updates_the_same_assistant_message(tmp_path) -> None:
    async def _impl() -> None:
        inf = await _infra(str(tmp_path))
        session_id = uuid.uuid4().hex
        await inf.chat_repo.create_session(
            session_id=session_id,
            user_id=USER.user_id,
            title="恢复生图",
        )
        message_id = await inf.chat_repo.append_message(
            session_id=session_id,
            role="assistant",
            content="生图任务详情如下：",
            job_id="job-1",
        )

        await inf.chat_repo.update_assistant_message(
            session_id=session_id,
            message_id=message_id,
            content="已完成，可在结果区查看。",
        )

        transcript = await inf.chat_repo.get_transcript(session_id, USER.user_id)
        assert transcript is not None
        assert len(transcript.messages) == 1
        assert transcript.messages[0].content == "已完成，可在结果区查看。"
        assert transcript.messages[0].job_id == "job-1"

    asyncio.run(_impl())
```

- [ ] **Step 2: Run the repository test and verify RED**

Run from `image-code`:

```powershell
uv run pytest tests/test_chat.py::test_chat_repository_updates_the_same_assistant_message -q
```

Expected: FAIL because `append_message` returns `None` and `update_assistant_message` does not exist.

- [ ] **Step 3: Change the repository port and SQL implementation**

In `ChatSessionRepository`, change the return type and add the update operation:

```python
async def append_message(
    self,
    *,
    session_id: str,
    role: str,
    content: str,
    job_id: str | None = None,
    attachment_upload_ids: tuple[str, ...] = (),
) -> str:
    """Append a transcript message and return its stable message id."""
    ...

@abstractmethod
async def update_assistant_message(
    self,
    *,
    session_id: str,
    message_id: str,
    content: str,
) -> None:
    """Update one assistant message without changing seq or job_id."""
    ...
```

In `SqlAlchemyChatSessionRepository.append_message`, create `message_id = uuid.uuid4().hex`, use it for `ChatMessageRow.id`, commit, and return it. Implement `update_assistant_message` by selecting the row with all three invariants:

```python
stmt = select(ChatMessageRow).where(
    ChatMessageRow.id == message_id,
    ChatMessageRow.session_id == session_id,
    ChatMessageRow.role == "assistant",
)
message = (await session.execute(stmt)).scalar_one()
message.content = content
chat_session = await session.get(ChatSessionRow, session_id)
if chat_session is None:
    raise LookupError(f"chat session not found: {session_id}")
chat_session.updated_at = datetime.now(UTC)
await session.commit()
```

Use `scalar_one()` so missing or mismatched messages fail fast rather than being ignored.

- [ ] **Step 4: Run the repository test and verify GREEN**

```powershell
uv run pytest tests/test_chat.py::test_chat_repository_updates_the_same_assistant_message -q
```

Expected: PASS.

- [ ] **Step 5: Add a failing orchestrator test for the pre-event persistence boundary**

Replace the existing terminal-only assertion in `test_confirm_launches_job_and_forwards_job_events` with an incremental consumption test. Consume through `job_started`, query the transcript before consuming any `job_event`, then finish the same generator:

```python
stream = orch.handle_confirm(USER, sid, tok, "confirm")
prefix: list[tuple[str, dict]] = []
async for event in stream:
    prefix.append((event.type, event.data))
    if event.type == "job_started":
        break

job_id = _first(prefix, "job_started")["job_id"]
running = await inf.chat_repo.get_transcript(sid, USER.user_id)
assert running is not None
assert [message.job_id for message in running.messages] == [None, job_id]
assert running.messages[1].content == "生图任务详情如下："

suffix = [(event.type, event.data) async for event in stream]
assert any(
    event_type == "job_event" and data["type"] == "task_completed"
    for event_type, data in suffix
)

completed = await inf.chat_repo.get_transcript(sid, USER.user_id)
assert completed is not None
assert len(completed.messages) == 2
assert completed.messages[1].job_id == job_id
assert completed.messages[1].content == "已完成，可在结果区查看。"
```

Use the concrete `ChatEvent.type` and `.data` attributes returned by the async iterator; do not wrap production behavior in a mock.

- [ ] **Step 6: Run the orchestrator test and verify RED**

```powershell
uv run pytest tests/test_chat.py::test_confirm_launches_job_and_forwards_job_events -q
```

Expected: FAIL because the assistant `job_id` message is absent at `job_started` time.

- [ ] **Step 7: Persist and later update the same task message**

In `ChatOrchestrator.handle_confirm`, immediately after `_launch` succeeds and before yielding `job_started`, add:

```python
job_message_id = await self.chat_repo.append_message(
    session_id=session_id,
    role="assistant",
    content="生图任务详情如下：",
    job_id=job_id,
)
```

Keep the existing `job_started` event unchanged. At the terminal closing section, replace the final `append_message(..., job_id=job_id)` call with:

```python
await self.chat_repo.update_assistant_message(
    session_id=session_id,
    message_id=job_message_id,
    content=closing,
)
```

All non-generation callers may ignore the returned message ID. Do not add compatibility overloads or a second terminal message.

- [ ] **Step 8: Add the fail-fast and cancellation regression assertions**

Add this test, patching `append_message` only after the confirmation token has been created so the initial user transcript remains real:

```python
def test_confirm_does_not_emit_job_started_when_anchor_write_fails(
    tmp_path, monkeypatch
) -> None:
    async def _impl() -> None:
        inf = await _infra(str(tmp_path))
        uid = await _stage(inf)
        orch = inf.orch(StubTextLLM(("", _gen_tc(uid, n=1))))
        planned = await _drain(orch.handle_message(USER, None, "生成一张图", [uid]))
        session_id = _first(planned, "session")["session_id"]
        token = _first(planned, "generation_confirm")["confirm_token"]

        async def fail_anchor(**_kwargs: object) -> str:
            raise RuntimeError("anchor write failed")

        monkeypatch.setattr(inf.chat_repo, "append_message", fail_anchor)
        stream = orch.handle_confirm(USER, session_id, token, "confirm")
        first = await anext(stream)
        assert first.type == "session"
        with pytest.raises(RuntimeError, match="anchor write failed"):
            await anext(stream)

    asyncio.run(_impl())
```

Retain the existing cancel test assertion that no `job_started` occurs and add this exact repository assertion after cancellation:

```python
assert await inf.chat_repo.job_count(session_id) == 0
```

Add an isolation test using two real repository sessions:

```python
def test_running_job_anchors_remain_isolated_between_sessions(tmp_path) -> None:
    async def _impl() -> None:
        inf = await _infra(str(tmp_path))
        session_a = uuid.uuid4().hex
        session_b = uuid.uuid4().hex
        await inf.chat_repo.create_session(
            session_id=session_a, user_id=USER.user_id, title="A"
        )
        await inf.chat_repo.create_session(
            session_id=session_b, user_id=USER.user_id, title="B"
        )
        await inf.chat_repo.append_message(
            session_id=session_a, role="assistant", content="任务 A", job_id="job-a"
        )
        await inf.chat_repo.append_message(
            session_id=session_b, role="assistant", content="任务 B", job_id="job-b"
        )

        transcript_a = await inf.chat_repo.get_transcript(session_a, USER.user_id)
        transcript_b = await inf.chat_repo.get_transcript(session_b, USER.user_id)
        assert transcript_a is not None and transcript_b is not None
        assert [message.job_id for message in transcript_a.messages] == ["job-a"]
        assert [message.job_id for message in transcript_b.messages] == ["job-b"]

    asyncio.run(_impl())
```

- [ ] **Step 9: Run backend focused and full quality gates**

```powershell
uv run pytest tests/test_chat.py -q
uv run ruff check src tests/test_chat.py
uv run mypy src
```

Expected: all commands pass with no new warnings.

- [ ] **Step 10: Commit the backend unit**

```powershell
git add image-code/src/design_hub/ports/chat_repository.py image-code/src/design_hub/infrastructure/db/chat_repo.py image-code/src/design_hub/application/chat/orchestrator.py image-code/tests/test_chat.py
git commit -m "feat: persist running chat generation jobs" -m "Anchor each submitted image job to its chat transcript before job_started and update the same assistant message on completion. This makes running jobs discoverable after session switches or page reloads without changing the database schema or SSE contract."
```

---

### Task 2: Reconstruct live result slots from persisted job detail

**Files:**
- Modify: `image-web/src/lib/listing.test.ts`
- Modify: `image-web/src/lib/listing.ts`
- Modify: `image-web/src/components/chat/ChatResultBlock.test.ts`
- Modify: `image-web/src/components/chat/ChatResultBlock.tsx`

**Interfaces:**
- Produces: `detailToResultSlots(detail: ListingJobDetail): ResultSlotLike[]` with generating-state padding to `detail.n`.
- Produces: `countProcessedSlots(slots: readonly ResultSlotLike[]): number`.
- Consumes: existing `ListingJobDetail`, `JOB_STATUS`, `IMAGE_SUCCESS_STATUS`.

- [ ] **Step 1: Write failing slot reconstruction tests**

In the existing `detailToResultSlots` suite, replace the “生成中为空” expectation with:

```typescript
it('生成中零结果：按 n 恢复完整等待槽', () => {
  expect(
    detailToResultSlots(detail({ status: JOB_STATUS.generating, n: 3, images: [] })),
  ).toEqual([{ url: null }, { url: null }, { url: null }])
})

it('生成中部分结果：保留成功和失败并补齐剩余等待槽', () => {
  const slots = detailToResultSlots(detail({
    status: JOB_STATUS.generating,
    n: 4,
    error: '场景：provider 500',
    images: [okImg('k1', '白底'), failImg('场景')],
  }))

  expect(slots).toEqual([
    { url: 'http://x/k1.png', imageType: '白底', imageKey: 'k1' },
    { url: null, imageType: '场景', error: '场景：provider 500' },
    { url: null },
    { url: null },
  ])
  expect(countProcessedSlots(slots)).toBe(2)
})
```

Import `countProcessedSlots` from `@/lib/listing`.

- [ ] **Step 2: Run the listing tests and verify RED**

Run from `image-web`:

```powershell
npm test -- src/lib/listing.test.ts
```

Expected: FAIL because generating details are not padded and `countProcessedSlots` is missing.

- [ ] **Step 3: Implement generating-state padding and processed counting**

Refactor `detailToResultSlots` so image rows are mapped once, then only generating jobs are padded:

```typescript
export function countProcessedSlots(slots: readonly ResultSlotLike[]): number {
  return slots.filter((slot) => Boolean(slot.url || slot.error || slot.unavailable)).length
}

export function detailToResultSlots(detail: ListingJobDetail): ResultSlotLike[] {
  const slots = detail.images.map(imageToResultSlot(detail.error))
  if (detail.status === JOB_STATUS.generating) {
    return [
      ...slots,
      ...Array.from(
        { length: Math.max(0, detail.n - slots.length) },
        () => ({ url: null }) as ResultSlotLike,
      ),
    ]
  }
  if (slots.length > 0) return slots
  if (detail.status === JOB_STATUS.failed) {
    return [{ url: null, error: detail.error ?? '出图失败' }]
  }
  return []
}
```

Extract `imageToResultSlot(error)` as a focused private mapper using the existing success, unavailable and failure rules. Do not truncate anomalous extra images when `images.length > n`.

- [ ] **Step 4: Run slot tests and verify GREEN**

```powershell
npm test -- src/lib/listing.test.ts
```

Expected: PASS, including all existing terminal-state tests.

- [ ] **Step 5: Add a failing result-card test for failed slots counting as processed**

Render `ChatResultBlock` with one successful slot, one failed slot and one waiting slot; pass `done={countProcessedSlots(slots)}` and `total={3}`. Assert the markup contains `2/3`, `生成失败`, and a loading indicator. Add an accessible label `aria-label="图片生成中"` to the pending slot spinner expectation.

- [ ] **Step 6: Run the component test and verify RED**

```powershell
npm test -- src/components/chat/ChatResultBlock.test.ts
```

Expected: FAIL because the pending spinner has no `图片生成中` accessible label.

- [ ] **Step 7: Add the pending-slot accessible state**

Add `role="status"` and `aria-label="图片生成中"` to the pending slot spinner container or spinner element. Keep unavailable, error and image action behavior unchanged.

- [ ] **Step 8: Run focused frontend tests**

```powershell
npm test -- src/lib/listing.test.ts src/components/chat/ChatResultBlock.test.ts
```

Expected: PASS.

- [ ] **Step 9: Commit the slot reconstruction unit**

```powershell
git add image-web/src/lib/listing.ts image-web/src/lib/listing.test.ts image-web/src/components/chat/ChatResultBlock.tsx image-web/src/components/chat/ChatResultBlock.test.ts
git commit -m "feat: reconstruct running image result slots" -m "Build complete placeholder grids from persisted generating job details, count successful and failed slots as processed, and expose an accessible pending state without changing terminal result behavior."
```

---

### Task 3: Poll running jobs and unify current/history rendering

**Files:**
- Modify: `image-web/src/api/listing.test.ts`
- Modify: `image-web/src/api/listing.ts`
- Create: `image-web/src/components/chat/ChatJobResult.tsx`
- Create: `image-web/src/components/chat/ChatJobResult.test.ts`
- Modify: `image-web/src/pages/ChatPage.tsx`
- Modify: `image-web/src/lib/chat.ts`
- Modify: `image-web/src/lib/chat.test.ts`

**Interfaces:**
- Produces: `listingJobQueryKey(jobId: string): readonly ['listing', 'job', string]`.
- Produces: `listingJobRefetchInterval(status: string | undefined): 1500 | false`.
- Produces: `ChatJobResult` with the existing preview/edit/background/reverse-prompt callbacks.
- Consumes: `detailToResultSlots`, `countProcessedSlots`, `useListingJob`.

- [ ] **Step 1: Write failing polling-policy tests**

Extend `image-web/src/api/listing.test.ts`:

```typescript
import { listingJobQueryKey, listingJobRefetchInterval, postJson } from '@/api/listing'
import { JOB_STATUS } from '@/lib/listing'

it('polls only while a job is generating', () => {
  expect(listingJobRefetchInterval(JOB_STATUS.generating)).toBe(1500)
  expect(listingJobRefetchInterval(JOB_STATUS.done)).toBe(false)
  expect(listingJobRefetchInterval(JOB_STATUS.partial)).toBe(false)
  expect(listingJobRefetchInterval(JOB_STATUS.failed)).toBe(false)
  expect(listingJobRefetchInterval(undefined)).toBe(false)
})

it('uses one stable query key for live and restored jobs', () => {
  expect(listingJobQueryKey('job-1')).toEqual(['listing', 'job', 'job-1'])
})
```

- [ ] **Step 2: Run the API tests and verify RED**

```powershell
npm test -- src/api/listing.test.ts
```

Expected: FAIL because both helpers are missing.

- [ ] **Step 3: Implement the shared key and conditional polling**

In `image-web/src/api/listing.ts`:

```typescript
export function listingJobQueryKey(jobId: string) {
  return ['listing', 'job', jobId] as const
}

export function listingJobRefetchInterval(status: string | undefined): 1500 | false {
  return status === JOB_STATUS.generating ? 1500 : false
}

export function useListingJob(jobId: string | undefined) {
  return useQuery({
    queryKey: listingJobQueryKey(jobId ?? ''),
    queryFn: () => authGet<ListingJobDetail>(`/listing/jobs/${jobId}`),
    enabled: Boolean(jobId),
    refetchInterval: (query) => listingJobRefetchInterval(query.state.data?.status),
  })
}
```

Import `JOB_STATUS`. The query function remains disabled when no ID exists; do not add polling before the first successful detail response.

- [ ] **Step 4: Run the API tests and verify GREEN**

```powershell
npm test -- src/api/listing.test.ts
```

Expected: PASS.

- [ ] **Step 5: Write failing tests for the shared job result view**

Create `ChatJobResult.test.ts` around an exported pure `ChatJobResultView`. The repository's Vitest include pattern is `src/**/*.test.ts`, so this createElement-based test must use `.test.ts`. Define concrete fixtures and render these states with `renderToStaticMarkup`:

```typescript
const actions = {
  onPreview: () => undefined,
  onEdit: () => undefined,
  onBackground: () => undefined,
  onReversePrompt: () => undefined,
}

const detail = (overrides: Partial<ListingJobDetail> = {}): ListingJobDetail => ({
  job_id: 'job-1',
  prompt: '',
  modifiers: {},
  platform: null,
  ratio: '1:1',
  size: '1024x1024',
  n: 3,
  status: JOB_STATUS.generating,
  total_cost: '0',
  error: null,
  created_at: '2026-08-06T00:00:00Z',
  completed_at: null,
  images: [],
  input_urls: [],
  input_roles: [],
  ...overrides,
} as ListingJobDetail)

const successfulImage = {
  url: 'https://img/k1.png',
  available: true,
  image_key: 'k1',
  seed: 1,
  cost: '0.05',
  status: IMAGE_SUCCESS_STATUS,
  image_type: '白底',
} as ListingJobImage

it('renders persisted progress with completed and pending slots', () => {
  const html = renderToStaticMarkup(createElement(ChatJobResultView, {
    detail: detail({ images: [successfulImage] }),
    loading: false,
    error: false,
    ...actions,
  }))
  expect(html).toContain('1/3')
  expect(html).toContain('图片生成中')
  expect(html).toContain('https://img/k1.png')
})

it('renders explicit loading and unavailable states', () => {
  const renderView = (loading: boolean, error: boolean) =>
    renderToStaticMarkup(createElement(ChatJobResultView, {
      detail: undefined,
      loading,
      error,
      ...actions,
    }))
  expect(renderView(true, false)).toContain('正在载入出图结果')
  expect(renderView(false, true)).toContain('出图结果已失效或无法载入')
})
```

Use real `ListingJobDetail` fixtures matching the generated OpenAPI type. Do not mock `ChatResultBlock`.

- [ ] **Step 6: Run the new component tests and verify RED**

```powershell
npm test -- src/components/chat/ChatJobResult.test.ts
```

Expected: FAIL because `ChatJobResultView` does not exist.

- [ ] **Step 7: Create the unified result component**

Move the loading/error/detail rendering currently inside `ChatPage.JobResult` into `ChatJobResult.tsx`:

```typescript
export interface ChatJobResultProps {
  jobId: string
  onPreview: (image: ChatPreviewImage) => void
  onEdit: (source: ChatEditSource) => void
  onBackground: (source: ChatEditSource) => void
  onReversePrompt: (source: ChatEditSource) => void
}

export interface ChatJobResultViewProps
  extends Omit<ChatJobResultProps, 'jobId'> {
  detail: ListingJobDetail | undefined
  loading: boolean
  error: boolean
}

export function ChatJobResult(props: ChatJobResultProps) {
  const query = useListingJob(props.jobId)
  const { jobId: _jobId, ...viewProps } = props
  return (
    <ChatJobResultView
      detail={query.data}
      loading={query.isLoading}
      error={Boolean(query.error)}
      {...viewProps}
    />
  )
}
```

`ChatJobResultView` computes `slots = detailToResultSlots(detail)`, `done = countProcessedSlots(slots)`, and renders `ChatResultBlock`. It returns `null` only when a successfully loaded terminal detail legitimately maps to no slots. Loading and query errors use the existing Chinese copy.

- [ ] **Step 8: Run the shared component tests and verify GREEN**

```powershell
npm test -- src/components/chat/ChatJobResult.test.ts
```

Expected: PASS.

- [ ] **Step 9: Write a failing reducer test for removing the duplicate SSE slot store**

Change the existing `confirm flow` test in `image-web/src/lib/chat.test.ts` to assert:

```typescript
let state = pushUserMessage(initialChatState(), '生成三张图')
state = applyChatEvent(state, {
  kind: 'generation_confirm',
  confirm: {
    confirmToken: 'ct_1',
    tool: 'generate',
    count: 3,
    modelId: 'gpt-image-2',
    modelDisplayName: 'GPT Image 2',
    renderTier: 'standard',
    ratio: '1:1',
  },
})
state = applyChatEvent(state, {
  kind: 'assistant_end',
  status: 'awaiting_confirm',
})
state = clearAwaiting(state)
state = applyChatEvent(state, {
  kind: 'job_started',
  jobId: 'j1',
  tool: 'generate',
  count: 3,
})
expect(state.awaiting).toBeNull()
expect(state.bubbles.at(-1)?.jobId).toBe('j1')

const afterImageEvent = applyChatEvent(state, {
  kind: 'job',
  jobId: 'j1',
  inner: { kind: 'image', url: 'http://x/a.png', imageType: '白底' },
  imageType: '白底',
})
expect(afterImageEvent).toBe(state)
```

Remove expectations for `state.slots`, `jobDone`, and `jobTotal` from this test.

- [ ] **Step 10: Run the reducer test and verify RED**

```powershell
npm test -- src/lib/chat.test.ts
```

Expected: FAIL because `job_started` still creates slot state and job events still mutate it.

- [ ] **Step 11: Remove the duplicate result state and integrate the shared component**

In `ChatState`, remove `slots`, `jobDone`, `jobTotal`, and `activeJobId`. In `initialChatState`, remove their initialization. Change reducer behavior to attach the job to the assistant bubble that already owns the generation confirmation:

```typescript
case 'job_started': {
  const index = lastAssistant(state.bubbles)
  if (index < 0) throw new Error('job_started requires an assistant bubble')
  const bubbles = [...state.bubbles]
  bubbles[index] = { ...bubbles[index], jobId: ev.jobId }
  return { ...state, bubbles, awaiting: null }
}
case 'job':
  return state
```

In `ChatPage.tsx`:

- import `ChatJobResult` and `listingJobQueryKey`;
- remove local `JobResult` and `CurrentJobResult` functions;
- render `ChatJobResult` for every historical bubble with `b.jobId`;
- rely on the same bubble mapping for current `job_started` events, because the reducer attaches the live job ID to its assistant bubble;
- update the scroll effect dependencies to exclude removed slot state;
- in the central event handler, invalidate `listingJobQueryKey(event.jobId)` for every `event.kind === 'job'` before applying the event.

Use:

```typescript
if (event.kind === 'job') {
  void qc.invalidateQueries({ queryKey: listingJobQueryKey(event.jobId) })
}
```

Do not create a separate cache key or retain the old SSE slots as a fallback.

- [ ] **Step 12: Run the integrated frontend tests**

```powershell
npm test -- src/lib/chat.test.ts src/lib/listing.test.ts src/api/listing.test.ts src/components/chat/ChatResultBlock.test.ts src/components/chat/ChatJobResult.test.ts
```

Expected: PASS.

- [ ] **Step 13: Run all frontend quality gates**

```powershell
npm test
npm run typecheck
npm run lint
npm run build
```

Expected: all commands pass without new warnings.

- [ ] **Step 14: Commit the unified frontend unit**

```powershell
git add image-web/src/api/listing.ts image-web/src/api/listing.test.ts image-web/src/components/chat/ChatJobResult.tsx image-web/src/components/chat/ChatJobResult.test.ts image-web/src/pages/ChatPage.tsx image-web/src/lib/chat.ts image-web/src/lib/chat.test.ts
git commit -m "feat: restore running chat image jobs" -m "Poll persisted generating jobs, rebuild complete result grids, and use one database-backed result component for both live and historical chat sessions. SSE now accelerates cache refresh without owning recoverable image progress."
```

---

### Task 4: Cross-feature regression verification

**Files:**
- Verify only; no production files should change.

**Interfaces:**
- Consumes: backend durable job anchor from Task 1.
- Consumes: frontend live-slot reconstruction and shared result query from Tasks 2–3.
- Produces: evidence that chat confirmation, session history, listing history and image actions remain compatible.

- [ ] **Step 1: Run the backend chat and API regression suite**

From `image-code`:

```powershell
uv run pytest tests/test_chat.py tests/test_chat_sse.py tests/test_chat_image_options.py tests/test_chat_ratio_intent.py tests/test_chat_image_ratio.py -q
uv run ruff check src tests
uv run mypy src
```

Expected: all selected tests and static checks pass.

- [ ] **Step 2: Run the full frontend suite again from a clean process**

From `image-web`:

```powershell
npm test
npm run typecheck
npm run lint
npm run build
```

Expected: all tests and build gates pass.

- [ ] **Step 3: Inspect the final diff for forbidden scope changes**

From the repository root:

```powershell
git diff HEAD~3 --check
git diff HEAD~3 --name-only
git status --short
```

Expected: only the implementation files listed in Tasks 1–3 are present in the three implementation commits; no migration, dependency manifest, generated OpenAPI schema, PRD, ops, or remote changes exist; working tree is clean.

- [ ] **Step 4: Record the verification result without an empty commit**

Do not create a verification-only commit. Report the exact commands and pass counts in the final handoff, together with the three implementation commit hashes. If a quality gate requires a code correction, return to the responsible task, add a failing regression test, make the minimal fix, rerun that task’s gates, and commit the correction with `fix: ...` plus a detailed body.
