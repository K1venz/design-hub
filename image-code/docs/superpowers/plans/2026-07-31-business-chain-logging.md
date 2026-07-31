# Production Business Chain Logging Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add explicit code-authored business-chain logs to API and Worker, expose them as an administrator-only timeline, and ship them in the same branch/release as the existing admin-list MySQL fix.

**Architecture:** Extend the existing structlog-compatible standard logging pipeline with a dedicated JSONL handler that only accepts `design_hub.*` records containing both `chain` and `action`. API and Worker write separate bounded files under the already shared, non-public exports volume; a read-only repository merges those files for manager-only list, detail, and trace APIs. Business code adds logs only at outcome-changing checkpoints, while the frontend renders the structured events without exposing the prompt in list responses.

**Tech Stack:** Python 3.12, standard `logging`/`RotatingFileHandler`, structlog, FastAPI, Pydantic, React, TypeScript, TanStack Query, Vitest.

## Global Constraints

- Only code-authored `design_hub.*` records with explicit `chain` and `action` enter the administrator log view.
- `info` means a business-chain checkpoint completed normally.
- `warning` means the application recognized and handled a business problem.
- `error` means a production, infrastructure, dependency, invariant, or unhandled system problem.
- Method names come from the actual Python `LogRecord.funcName`; they are not copied into string constants.
- List responses never contain `prompt`; manager-only detail and trace responses may contain the sanitized full prompt.
- API keys, tokens, passwords, cookies, Redis credentials, and signed query parameters remain redacted.
- Internal beta uses no TOS archive and no time-based retention promise.
- API and Worker each use at most 100 MB: a 50 MB current JSONL file plus one 50 MB rotated file.
- Runtime logs live at `./exports/.runtime-logs`; the production exports volume is shared by API and Worker and is not mounted into Nginx.
- Corrupt JSONL is a production error and fails the read request; it is never silently skipped.
- Do not add a logging framework, database table, Redis log stream, compatibility shim, or unrelated refactor.
- Keep commit `8d251c9` (`fix: make admin joins collation-safe`) in the same branch and production release; do not rewrite or squash its history.
- Backend commands run from `image-code`, frontend commands run from `image-web`, and cross-project Git commands run from the worktree root.

---

## File Structure

### Backend

- Create `src/design_hub/domain/runtime_logs.py`: immutable runtime-log entry, query, page, and corruption error types.
- Create `src/design_hub/ports/runtime_logs.py`: read-only runtime-log repository protocol.
- Create `src/design_hub/infrastructure/monitoring/runtime_log_files.py`: business-log filter, rotating JSONL handler construction, and bounded JSONL reader.
- Create `src/design_hub/application/admin/runtime_log_service.py`: list/detail/trace use cases.
- Create `src/design_hub/interface/api/routes/runtime_logs.py`: manager-only HTTP routes.
- Modify `src/design_hub/infrastructure/monitoring/logging.py`: code-location processor, runtime formatter, field allowlists, and optional runtime handler.
- Modify `src/design_hub/config/settings.py`: runtime-log directory and maximum file size.
- Modify `src/design_hub/interface/api/asgi.py`: configure the API handler and compose the reader/service.
- Modify `src/design_hub/interface/worker.py`: configure the Worker handler.
- Modify `src/design_hub/interface/api/deps.py`: expose the runtime-log service dependency.
- Modify `src/design_hub/interface/admin_console_schemas.py`: list, detail, and trace schemas.
- Modify key business files for explicit checkpoints:
  - `src/design_hub/application/listing/submission_service.py`
  - `src/design_hub/application/tasking/outbox_dispatcher.py`
  - `src/design_hub/application/tasking/worker.py`
  - `src/design_hub/application/tasking/runtime.py`
  - `src/design_hub/application/chat/orchestrator.py`
  - `src/design_hub/application/admin/model_capability_service.py`

### Frontend

- Modify `image-web/openapi.json`: generated backend contract.
- Modify `image-web/src/api/schema.d.ts`: generated TypeScript contract.
- Modify `image-web/src/api/admin.ts`: runtime-log filters and query hooks.
- Create `image-web/src/pages/AdminRuntimeLogsPage.tsx`: log list, filters, detail, and trace timeline.
- Create `image-web/src/pages/AdminRuntimeLogsPage.test.tsx`: rendering, prompt boundary, and error-state tests.
- Modify `image-web/src/components/admin/AdminLayout.tsx`: navigation item.
- Modify `image-web/src/App.tsx`: `/admin/logs` route.

---

### Task 1: Business-only structured file handler

**Files:**
- Create: `src/design_hub/infrastructure/monitoring/runtime_log_files.py`
- Modify: `src/design_hub/infrastructure/monitoring/logging.py`
- Modify: `src/design_hub/config/settings.py`
- Modify: `src/design_hub/interface/api/asgi.py`
- Modify: `src/design_hub/interface/worker.py`
- Test: `tests/test_task_observability.py`

**Interfaces:**
- Produces:
  - `is_business_chain_record(record: logging.LogRecord) -> bool`
  - `runtime_log_handler(directory: Path, service: Literal["api", "worker"], max_bytes: int) -> logging.Handler`
  - `configure_logging(*, level: int = logging.INFO, stream: TextIO | None = None, runtime_log_dir: Path | None = None, service: Literal["api", "worker"] | None = None, runtime_log_max_bytes: int = 50 * 1024 * 1024) -> None`
- Runtime JSON objects contain `event_id`, `timestamp`, `level`, `service`, `chain`, `event`, `action`, `logger`, `function`, and safe optional context.

- [ ] **Step 1: Write the failing handler contract tests**

Add tests that exercise the real logging pipeline:

```python
def test_runtime_file_only_contains_explicit_business_chain_logs(tmp_path: Path) -> None:
    configure_logging(
        stream=StringIO(),
        runtime_log_dir=tmp_path,
        service="api",
        runtime_log_max_bytes=1024,
    )
    logger = logging.getLogger("design_hub.example")
    logger.info("ordinary_internal_event")
    logger.info(
        "generation_task_created",
        extra={
            "chain": "image_generation",
            "action": "创建出图任务",
            "trace_id": "trace-1",
            "prompt": "完整提示词",
        },
    )

    rows = [
        json.loads(line)
        for line in (tmp_path / "api.jsonl").read_text().splitlines()
    ]
    assert len(rows) == 1
    assert rows[0]["event"] == "generation_task_created"
    assert rows[0]["function"] == (
        "test_runtime_file_only_contains_explicit_business_chain_logs"
    )
    assert rows[0]["prompt"] == "完整提示词"
```

Add separate assertions that:

- `uvicorn.access` records never enter the runtime file;
- the stdout formatter does not include `prompt`;
- the runtime formatter redacts `Bearer`, `sk-`, `password=`, and signed URL query values;
- a prompt longer than 1,000 characters remains complete after secret-pattern redaction;
- `api.jsonl` and `worker.jsonl` use distinct files;
- `maxBytes=50 MiB` and `backupCount=1`;
- a forced file-write error does not fail the business log call and emits one fixed, credential-free error to stderr/Sentry.

- [ ] **Step 2: Run the tests and verify RED**

Run:

```bash
uv run pytest tests/test_task_observability.py -q
```

Expected: FAIL because `configure_logging` does not accept runtime-log arguments and no JSONL file is created.

- [ ] **Step 3: Implement the minimal handler and formatters**

In `runtime_log_files.py`, implement a filter that accepts only records satisfying both conditions:

```python
def is_business_chain_record(record: logging.LogRecord) -> bool:
    return (
        record.name.startswith("design_hub.")
        and isinstance(getattr(record, "chain", None), str)
        and bool(record.chain)
        and isinstance(getattr(record, "action", None), str)
        and bool(record.action)
    )
```

Build one `RotatingFileHandler` per service:

```python
handler = RotatingFileHandler(
    directory / f"{service}.jsonl",
    maxBytes=max_bytes,
    backupCount=1,
    encoding="utf-8",
)
handler.addFilter(BusinessChainFilter())
```

Add a formatter processor that reads `_record.funcName` into `function`, sets `service`, and generates `event_id=uuid4().hex`. Keep two sanitizers:

- stdout sanitizer: existing safe fields, without `prompt`;
- runtime sanitizer: the same fields plus `service`, `chain`, `action`, `function`, `model`, and sanitized `prompt`;
- `_safe_prompt` applies credential and URL redaction without the existing 1,000-character truncation.

Subclass `RotatingFileHandler` only to override `handleError`. The override leaves the business call unaffected, captures the current exception with Sentry, writes the fixed text `runtime business log write failed` to stderr once per process, and never calls the logging pipeline recursively.

Add settings:

```python
runtime_log_dir: Path = Path("./exports/.runtime-logs")
runtime_log_max_bytes: int = Field(default=50 * 1024 * 1024, gt=0)
```

Configure API with `service="api"` and Worker with `service="worker"`.

- [ ] **Step 4: Run focused verification**

Run:

```bash
uv run pytest tests/test_task_observability.py -q
uv run ruff check src/design_hub/infrastructure/monitoring tests/test_task_observability.py
uv run mypy src/design_hub/infrastructure/monitoring src/design_hub/config/settings.py
```

Expected: all pass with no warnings or type errors.

- [ ] **Step 5: Commit**

```bash
git add \
  src/design_hub/infrastructure/monitoring/runtime_log_files.py \
  src/design_hub/infrastructure/monitoring/logging.py \
  src/design_hub/config/settings.py \
  src/design_hub/interface/api/asgi.py \
  src/design_hub/interface/worker.py \
  tests/test_task_observability.py
git commit -m "feat: persist explicit business chain logs" \
  -m "Write only code-authored chain events to bounded API and Worker JSONL files while preserving sanitized stdout logging."
```

### Task 2: Manager-only runtime-log query API

**Files:**
- Create: `src/design_hub/domain/runtime_logs.py`
- Create: `src/design_hub/ports/runtime_logs.py`
- Extend: `src/design_hub/infrastructure/monitoring/runtime_log_files.py`
- Create: `src/design_hub/application/admin/runtime_log_service.py`
- Create: `src/design_hub/interface/api/routes/runtime_logs.py`
- Modify: `src/design_hub/interface/admin_console_schemas.py`
- Modify: `src/design_hub/interface/api/deps.py`
- Modify: `src/design_hub/interface/api/asgi.py`
- Test: `tests/test_runtime_logs.py`

**Interfaces:**
- Produces:

```python
@dataclass(frozen=True)
class RuntimeLogQuery:
    level: str | None = None
    service: str | None = None
    chain: str | None = None
    trace_id: str | None = None
    job_id: str | None = None
    start: datetime | None = None
    end: datetime | None = None

@dataclass(frozen=True)
class RuntimeLogPage:
    items: tuple[RuntimeLogEntry, ...]
    total: int
    limit: int
    offset: int

class RuntimeLogRepository(Protocol):
    def list(
        self,
        query: RuntimeLogQuery,
        *,
        limit: int,
        offset: int,
    ) -> RuntimeLogPage:
        raise NotImplementedError

    def get(self, event_id: str) -> RuntimeLogEntry | None:
        raise NotImplementedError

    def trace(self, trace_id: str) -> tuple[RuntimeLogEntry, ...]:
        raise NotImplementedError
```

- HTTP routes:
  - `GET /admin/runtime-logs`
  - `GET /admin/runtime-logs/{event_id}`
  - `GET /admin/runtime-logs/{event_id}/trace`

- [ ] **Step 1: Write failing repository tests with real JSONL**

Create `api.jsonl`, `api.jsonl.1`, `worker.jsonl`, and `worker.jsonl.1` fixtures containing literal events. Assert:

```python
page = repository.list(
    RuntimeLogQuery(level="warning", chain="image_generation"),
    limit=20,
    offset=0,
)
assert [item.event_id for item in page.items] == ["warning-new", "warning-old"]
assert page.total == 2
assert repository.get("warning-new").prompt == "完整提示词"
assert [item.event_id for item in repository.trace("trace-1")] == [
    "created",
    "published",
    "completed",
]
```

Add one malformed JSON line and assert `RuntimeLogCorruptError` includes only the filename and line number, not the raw line.

- [ ] **Step 2: Write failing API boundary tests**

Build a FastAPI test app with the real routes and a temporary-file repository. Assert:

- list returns 200 without a `prompt` key;
- detail returns the sanitized full `prompt`;
- trace returns ascending timestamps;
- missing event returns 404;
- designer access returns 403;
- `limit=0`, `limit=201`, negative offset, invalid level, and reversed dates return 400 or 422.

- [ ] **Step 3: Run tests and verify RED**

Run:

```bash
uv run pytest tests/test_runtime_logs.py -q
```

Expected: FAIL because the domain types, repository, service, schemas, and routes do not exist.

- [ ] **Step 4: Implement the file reader and use case**

The reader scans only these fixed names:

```python
("api.jsonl", "api.jsonl.1", "worker.jsonl", "worker.jsonl.1")
```

For list queries:

- parse each non-empty line exactly once;
- validate required fields and ISO timestamp;
- count all matching rows;
- retain only `offset + limit` newest entries with `heapq.nlargest`;
- strip `prompt` when converting to the list schema.

For detail, scan until the exact `event_id` is found. For trace, collect exact `trace_id` matches and sort ascending.

Use synchronous methods because bounded local file reads are plain filesystem I/O; FastAPI routes call them through `run_in_threadpool` so the event loop is not blocked.

- [ ] **Step 5: Compose and register manager-only routes**

Build `RuntimeLogService` in the API lifespan from `settings.runtime_log_dir`, store it on `app.state`, and include the router with the existing `manager_only` dependency list.

Schemas must use separate types:

```python
class RuntimeLogListItemOut(BaseModel):
    event_id: str
    timestamp: datetime
    level: Literal["info", "warning", "error"]
    service: Literal["api", "worker"]
    chain: str
    event: str
    action: str
    logger: str
    function: str
    trace_id: str
    job_id: str | None
    model: str | None
    status: str | None
    duration_ms: int | None

class RuntimeLogDetailOut(RuntimeLogListItemOut):
    request_id: str | None
    item_id: str | None
    operation_id: str | None
    provider: str | None
    error_code: str | None
    error_type: str | None
    error_summary: str | None
    prompt: str | None
```

- [ ] **Step 6: Run focused verification**

Run:

```bash
uv run pytest tests/test_runtime_logs.py tests/test_task_observability.py -q
uv run ruff check src/design_hub/domain/runtime_logs.py src/design_hub/ports/runtime_logs.py \
  src/design_hub/infrastructure/monitoring/runtime_log_files.py \
  src/design_hub/application/admin/runtime_log_service.py \
  src/design_hub/interface/api/routes/runtime_logs.py tests/test_runtime_logs.py
uv run mypy src/design_hub/domain/runtime_logs.py src/design_hub/ports/runtime_logs.py \
  src/design_hub/infrastructure/monitoring/runtime_log_files.py \
  src/design_hub/application/admin/runtime_log_service.py \
  src/design_hub/interface/api/routes/runtime_logs.py
```

Expected: all pass.

- [ ] **Step 7: Commit**

```bash
git add \
  src/design_hub/domain/runtime_logs.py \
  src/design_hub/ports/runtime_logs.py \
  src/design_hub/infrastructure/monitoring/runtime_log_files.py \
  src/design_hub/application/admin/runtime_log_service.py \
  src/design_hub/interface/api/routes/runtime_logs.py \
  src/design_hub/interface/admin_console_schemas.py \
  src/design_hub/interface/api/deps.py \
  src/design_hub/interface/api/asgi.py \
  tests/test_runtime_logs.py
git commit -m "feat: expose manager runtime log timelines" \
  -m "Read bounded API and Worker business logs through manager-only list, detail, and trace endpoints without exposing prompts in list responses."
```

### Task 3: Explicit logs at business-chain checkpoints

**Files:**
- Modify: `src/design_hub/application/listing/submission_service.py`
- Modify: `src/design_hub/application/tasking/outbox_dispatcher.py`
- Modify: `src/design_hub/application/tasking/worker.py`
- Modify: `src/design_hub/application/tasking/runtime.py`
- Modify: `src/design_hub/application/chat/orchestrator.py`
- Modify: `src/design_hub/application/admin/model_capability_service.py`
- Test: `tests/test_business_chain_events.py`
- Test: existing focused tests for each modified service

**Interfaces:**
- Every event supplies concrete `chain` and `action` values plus the identifiers available at that checkpoint.
- Stable chain identifiers:
  - `image_generation`
  - `chat`
  - `reverse_prompt`
  - `model_configuration`
- Stable event names and levels:

| Event | Level | Action |
|---|---|---|
| `generation_task_created` | info | 创建出图任务 |
| `generation_outbox_published` | info | 发布任务到队列 |
| `generation_item_claimed` | info | Worker领取生成任务 |
| `generation_provider_submit_started` | info | 开始调用图片模型 |
| `generation_item_completed` | info | 保存图片并完成任务 |
| `generation_item_duplicate_terminal` | warning | 忽略重复投递的终态任务 |
| `generation_model_unavailable` | warning | 用户选择的模型不可用 |
| `generation_provider_rejected` | warning | 模型拒绝业务请求 |
| `generation_provider_failed` | error | 图片模型调用失败 |
| `generation_delivery_failed` | error | Worker任务执行异常 |
| `chat_model_started` | info | 开始调用对话模型 |
| `chat_model_completed` | info | 对话模型调用完成 |
| `chat_model_unavailable` | warning | 对话模型未启用 |
| `chat_model_failed` | error | 对话模型调用失败 |
| `reverse_prompt_completed` | info | 完成图片提示词反推 |
| `reverse_prompt_rejected` | warning | 反推提示词输入不满足要求 |
| `reverse_prompt_failed` | error | 反推提示词模型调用失败 |
| `model_capability_test_started` | info | 开始模型连通性测试 |
| `model_capability_test_completed` | info | 模型连通性测试成功 |
| `model_capability_test_rejected` | warning | 模型配置未通过业务校验 |
| `model_capability_test_failed` | error | 模型连通性测试发生系统错误 |

- [ ] **Step 1: Write failing event-contract tests**

Use a real `logging.Handler` that captures `LogRecord` instances. Exercise existing service fakes and assert records, not mocks:

```python
record = next(item for item in records if item.msg == "generation_item_completed")
assert record.levelno == logging.INFO
assert record.chain == "image_generation"
assert record.action == "保存图片并完成任务"
assert record.job_id == "job-1"
assert record.item_id == "item-1"
```

Add independent tests for:

- terminal duplicate is `warning`, not `info`;
- model unavailable is `warning`;
- `DomainError` from a model call is `warning`;
- `ProviderTimeout`, generic `ProviderError`, task invariant failure, and storage failure are `error`;
- provider-start record contains `model` and full final `prompt`;
- Chat model unavailable is `warning`, while `TextLLMError` is `error`;
- reverse-prompt validation failure is `warning`;
- model capability test success emits start and completed `info`.

- [ ] **Step 2: Run tests and verify RED**

Run:

```bash
uv run pytest tests/test_business_chain_events.py -q
```

Expected: FAIL because the explicit chain fields and required event records are absent or use the wrong level.

- [ ] **Step 3: Implement image-chain events**

Update existing log calls instead of adding duplicate records. The provider-start checkpoint must include:

```python
extra={
    **self._log_context(delivery, work),
    "chain": "image_generation",
    "action": "开始调用图片模型",
    "model": work.spec.model,
    "prompt": work.spec.final_prompt,
}
```

Add `generation_item_claimed` after a successful repository claim. Log `ModelUnavailableError` as `warning` before failing and acknowledging the item.

Classify provider outcomes without changing provider retry or task-state behavior:

- handled `DomainError`: `warning`;
- `ProviderTimeout`: `error`;
- other `ProviderError`: `error`;
- unhandled runtime callback exception: `error`.

Change the existing terminal-duplicate log from `info` to `warning`.

- [ ] **Step 4: Implement Chat, reverse-prompt, and model-test events**

Add one start and one terminal event around the real external model calls. Split combined catch clauses so the level is exact:

```python
except ModelUnavailableError:
    logger.warning(
        "chat_model_unavailable",
        extra={
            "chain": "chat",
            "action": "对话模型未启用",
            "status": "unavailable",
        },
    )
except TextLLMError:
    logger.error(
        "chat_model_failed",
        extra={
            "chain": "chat",
            "action": "对话模型调用失败",
            "status": "failed",
        },
        exc_info=True,
    )
```

For reverse prompt, keep `ValueError`, `NotFoundError`, and `UploadReadError` as `warning`; keep `TextLLMError` as `error`.

For capability tests:

- emit started `info` only after local validation and concurrency admission;
- emit completed `info` only after proof issuance;
- log `CapabilityTestBusy` and invalid configuration as `warning`;
- log provider/network/storage failures as `error` and re-raise unchanged.

- [ ] **Step 5: Run focused and regression tests**

Run:

```bash
uv run pytest \
  tests/test_business_chain_events.py \
  tests/test_generation_worker.py \
  tests/test_task_observability.py \
  tests/test_chat.py \
  tests/test_reverse_prompt.py \
  tests/test_model_config.py -q
uv run ruff check src/design_hub/application tests/test_business_chain_events.py
uv run mypy src/design_hub/application
```

Expected: all pass and existing task behavior remains unchanged.

- [ ] **Step 6: Commit**

```bash
git add \
  src/design_hub/application/listing/submission_service.py \
  src/design_hub/application/tasking/outbox_dispatcher.py \
  src/design_hub/application/tasking/worker.py \
  src/design_hub/application/tasking/runtime.py \
  src/design_hub/application/chat/orchestrator.py \
  src/design_hub/application/admin/model_capability_service.py \
  tests/test_business_chain_events.py
git commit -m "feat: classify business chain checkpoints" \
  -m "Emit explicit chain, action, method, context, and severity metadata at image, chat, reverse-prompt, and model-test outcome boundaries."
```

### Task 4: Administrator runtime-log page

**Files:**
- Modify: `image-web/openapi.json`
- Modify: `image-web/src/api/schema.d.ts`
- Modify: `image-web/src/api/admin.ts`
- Create: `image-web/src/pages/AdminRuntimeLogsPage.tsx`
- Create: `image-web/src/pages/AdminRuntimeLogsPage.test.tsx`
- Modify: `image-web/src/components/admin/AdminLayout.tsx`
- Modify: `image-web/src/App.tsx`

**Interfaces:**
- Route: `/admin/logs`
- Query hooks:

```ts
export interface RuntimeLogFilters {
  level?: 'info' | 'warning' | 'error'
  service?: 'api' | 'worker'
  chain?: string
  trace_id?: string
  job_id?: string
  start?: string
  end?: string
  limit?: number
  offset?: number
}

useRuntimeLogs(filters: RuntimeLogFilters)
useRuntimeLogDetail(eventId: string | undefined)
useRuntimeLogTrace(eventId: string | undefined)
```

- [ ] **Step 1: Regenerate and verify the API contract**

Run:

```bash
(cd image-code && uv run python -c 'import json; from design_hub.interface.api.asgi import create_production_app; print(json.dumps(create_production_app().openapi(), ensure_ascii=False, indent=2))') > image-web/openapi.json
(cd image-web && npm run gen:api)
```

Run this block from the worktree root.

Confirm generated paths include all three `/admin/runtime-logs` contracts.

- [ ] **Step 2: Write failing hook and page tests**

Use a real QueryClient and stub only HTTP responses. Assert:

- list renders level, service, chain, `logger.function`, action, model, status, and duration;
- list markup never renders the prompt returned only by the detail fixture;
- clicking a row opens a dialog and renders the complete prompt;
- trace nodes render ascending timestamps and highlight the selected `event_id`;
- level/service/chain filters reach the request query;
- API error renders a retry action without clearing current filter values;
- `warning` and `error` have distinct accessible labels, not color-only meaning.

Expected test fixture:

```ts
const detail = {
  event_id: 'event-2',
  timestamp: '2026-07-31T09:00:00Z',
  level: 'warning',
  service: 'worker',
  chain: 'image_generation',
  event: 'generation_provider_rejected',
  action: '模型拒绝业务请求',
  logger: 'design_hub.application.tasking.worker',
  function: '_fail_provider',
  trace_id: 'trace-1',
  prompt: '完整提示词',
}
```

- [ ] **Step 3: Run tests and verify RED**

Run:

```bash
npm test -- --run src/pages/AdminRuntimeLogsPage.test.tsx
```

Expected: FAIL because the hooks, page, route, and navigation item do not exist.

- [ ] **Step 4: Implement typed hooks**

Add runtime-log keys under `adminKeys.logsRoot`, `adminKeys.logs(filters)`, `adminKeys.log(eventId)`, and `adminKeys.logTrace(eventId)`. Use generated `components["schemas"]` types; do not duplicate backend response types.

- [ ] **Step 5: Implement the page**

Follow the existing admin visual language:

- compact filters above the table;
- newest-first rows;
- badges with text `正常`、`业务问题`、`系统问题`;
- code location displayed as `${logger}.${function}`;
- a dialog for detail and trace;
- prompt rendered in a wrapped, selectable `<pre>`;
- trace sorted from earliest to latest;
- skeleton, empty, retry, and pagination states.

Add navigation label `运行日志` and route `/admin/logs`.

- [ ] **Step 6: Run frontend verification**

Run:

```bash
npm test -- --run src/pages/AdminRuntimeLogsPage.test.tsx src/lib/admin.test.ts
npm run typecheck
npm run lint
npm run build
```

Expected: all pass; the build may retain the existing chunk-size warning but no errors.

- [ ] **Step 7: Commit**

```bash
git add \
  openapi.json \
  src/api/schema.d.ts \
  src/api/admin.ts \
  src/pages/AdminRuntimeLogsPage.tsx \
  src/pages/AdminRuntimeLogsPage.test.tsx \
  src/components/admin/AdminLayout.tsx \
  src/App.tsx
git commit -m "feat: add administrator chain log viewer" \
  -m "Render manager-only business log filters, details, complete prompts, and correlated trace timelines from the typed runtime-log API."
```

### Task 5: Integrated verification and production release

**Files:**
- Verify: all files changed by Tasks 1–4
- Release with existing commit: `8d251c9 fix: make admin joins collation-safe`

**Interfaces:**
- Production manager route: `https://image.sepaitech.com/admin/logs`
- Production API routes:
  - `/api/admin/runtime-logs`
  - `/api/admin/runtime-logs/{event_id}`
  - `/api/admin/runtime-logs/{event_id}/trace`

- [ ] **Step 1: Run the backend regression suite**

Run:

```bash
uv run pytest -q
uv run ruff check src tests
uv run mypy src
```

Expected: all tests and static checks pass.

- [ ] **Step 2: Run the frontend regression suite**

Run:

```bash
npm test -- --run
npm run typecheck
npm run lint
npm run build
```

Expected: all tests and checks pass; only the existing non-blocking bundle-size warning is allowed.

- [ ] **Step 3: Confirm branch composition**

Run:

```bash
git status --short
git log --oneline --decorate -8
git merge-base --is-ancestor 8d251c9 HEAD
```

Expected: clean worktree and exit 0 from the ancestor check.

- [ ] **Step 4: Deploy with the existing safe production workflow**

Build the frontend, sync committed `image-code` and `image-web/dist`, tag the current API image for rollback, build the new image, and run a one-off read-only production probe before replacing API/Worker. No database migration is expected.

- [ ] **Step 5: Verify production**

With the manager account:

1. call all three runtime-log endpoints and require HTTP 200;
2. confirm list JSON contains no `prompt`;
3. confirm detail JSON contains the sanitized full prompt;
4. run one controlled image task;
5. require the same `trace_id` to show task creation, queue publication, Worker claim, provider start, and completion;
6. confirm method names are populated from real code;
7. confirm `info`, controlled business rejection `warning`, and controlled test-environment infrastructure failure `error`;
8. confirm `/admin/users` and `/admin/images` still return HTTP 200;
9. confirm API, Worker, and Redis containers are healthy.

- [ ] **Step 6: Report the release**

Report:

- production URL;
- commit list including `8d251c9`;
- exact verification counts;
- any intentionally untested destructive fault injection;
- rollback image availability.
