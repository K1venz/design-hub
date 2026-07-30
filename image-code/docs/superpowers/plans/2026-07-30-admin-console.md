# Admin Console Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a unified manager-only console for user status, cross-user generation review, reversible image blocking, exact GPT Image request counts, Doubao Chat token usage, model configuration, and audited administrator actions.

**Architecture:** Add durable `model_call` and `admin_audit_log` records plus small extensions to `app_user` and `listing_image`. Keep ordinary owner-scoped reads intact; a separate admin query service supplies paginated management views, while provider-boundary metering records each real outbound model request. The existing React application gets one `/admin` shell that consumes the new manager-only APIs.

**Tech Stack:** Python 3.12, FastAPI, Pydantic 2, SQLAlchemy async, Alembic, MySQL/SQLite tests, httpx streaming, React 19, TypeScript 6, React Router 7, TanStack Query 5, Tailwind 4, Vitest.

## Global Constraints

- Follow the approved design in `image-code/docs/superpowers/specs/2026-07-30-admin-console-design.md`.
- Do not add automatic moderation, multi-level admin roles, CSV export, budget alerts, physical image deletion, storage cleanup, or user impersonation.
- GPT Image counts every actual `images/generations` or `images/edits` POST, including retries; async polling and CDN downloads never count.
- Doubao Chat records every actual Chat Completion request and its upstream input, output, and total tokens.
- Do not infer historical model-call counts or tokens.
- Existing and new users default to enabled; existing and new images default to `normal`.
- Blocking is reversible. Ordinary users lose preview, download, reverse-prompt, edit, and background-replacement access; managers retain review access.
- JWT signature verification is followed by a current database user lookup for both Bearer and SSE authentication.
- Admin mutations and their audit row commit in one database transaction.
- Never persist or return passwords, JWTs, API keys, authorization headers, raw image bytes, or duplicated full prompts in model-call or audit records.
- Keep ordinary user queries owner-scoped. Cross-user access belongs only in the admin query repository.
- Lists are server-paginated with stable ordering; images use on-demand signed URLs.
- No dependency additions are expected. If implementation proves otherwise, stop and explain before running a package-manager command.
- Repository boundary note: the approved feature necessarily changes `image-web/` and code-owned automated tests, while the current role card says Dev writes only `image-code/` and no tests. Execution must not cross those paths until the user explicitly authorizes that exception.

---

## File Map

### Backend files to create

- `image-code/migrations/versions/b8c9d0e1f2a3_admin_console_foundation.py` — schema migration and deterministic defaults.
- `image-code/src/design_hub/domain/admin.py` — moderation, model-call, and audit enums/value objects.
- `image-code/src/design_hub/ports/model_calls.py` — outbound-call context, usage, and recorder protocol.
- `image-code/src/design_hub/ports/admin_console.py` — paginated admin read models and mutation protocol.
- `image-code/src/design_hub/infrastructure/db/model_call_repo.py` — durable model-call start/finalization.
- `image-code/src/design_hub/infrastructure/db/admin_console_repo.py` — admin aggregates, paginated cross-user reads, user status, moderation, and audit reads.
- `image-code/src/design_hub/application/admin/admin_console_service.py` — validation and manager use cases.
- `image-code/src/design_hub/interface/admin_console_schemas.py` — HTTP request/response schemas.
- `image-code/src/design_hub/interface/api/routes/admin_console.py` — manager-only console endpoints.

### Backend files to modify

- `image-code/src/design_hub/infrastructure/db/models.py`
- `image-code/src/design_hub/ports/user_repository.py`
- `image-code/src/design_hub/infrastructure/db/user_repo.py`
- `image-code/src/design_hub/application/admin/user_admin_service.py`
- `image-code/src/design_hub/application/admin/model_config_service.py`
- `image-code/src/design_hub/infrastructure/db/model_config_repo.py`
- `image-code/src/design_hub/interface/api/deps.py`
- `image-code/src/design_hub/interface/api/admin_deps.py`
- `image-code/src/design_hub/interface/api/routes/users.py`
- `image-code/src/design_hub/interface/api/routes/admin.py`
- `image-code/src/design_hub/interface/api/asgi.py`
- `image-code/src/design_hub/interface/auth_schemas.py`
- `image-code/src/design_hub/ports/model_provider.py`
- `image-code/src/design_hub/ports/provider_execution.py`
- `image-code/src/design_hub/infrastructure/providers/mock.py`
- `image-code/src/design_hub/infrastructure/providers/openai_compat.py`
- `image-code/src/design_hub/infrastructure/providers/apinebula_async.py`
- `image-code/src/design_hub/infrastructure/providers/execution.py`
- `image-code/src/design_hub/application/tasking/worker.py`
- `image-code/src/design_hub/ports/text_llm.py`
- `image-code/src/design_hub/infrastructure/providers/mock_text.py`
- `image-code/src/design_hub/infrastructure/providers/openai_compat_text.py`
- `image-code/src/design_hub/application/chat/orchestrator.py`
- `image-code/src/design_hub/application/image_prompts/reverse_prompt.py`
- `image-code/src/design_hub/composition.py`
- `image-code/src/design_hub/ports/listing_query.py`
- `image-code/src/design_hub/infrastructure/db/listing_query_repo.py`
- `image-code/src/design_hub/interface/listing_history_schemas.py`

### Frontend files to create

- `image-web/src/components/admin/AdminLayout.tsx`
- `image-web/src/components/admin/AdminPagination.tsx`
- `image-web/src/components/admin/AdminMetricCard.tsx`
- `image-web/src/components/admin/ModerationDialog.tsx`
- `image-web/src/pages/AdminOverviewPage.tsx`
- `image-web/src/pages/AdminGenerationsPage.tsx`
- `image-web/src/pages/AdminGenerationDetailPage.tsx`
- `image-web/src/pages/AdminUsagePage.tsx`
- `image-web/src/pages/AdminAuditPage.tsx`

### Frontend files to modify

- `image-web/src/App.tsx`
- `image-web/src/api/admin.ts`
- `image-web/src/api/users.ts`
- `image-web/src/api/schema.d.ts` (generated)
- `image-web/src/components/layout/navigation.ts`
- `image-web/src/components/layout/navigation.test.ts`
- `image-web/src/pages/AdminUsersPage.tsx`
- `image-web/src/pages/AdminModelsPage.tsx`
- `image-web/src/pages/HistoryPage.tsx`
- `image-web/src/pages/HistoryDetailPage.tsx`
- `image-web/src/components/listing/ResultGallery.tsx`
- `image-web/src/components/chat/ChatResultBlock.tsx`
- `image-web/src/lib/listing.ts`
- `image-web/openapi.json` (generated)

### Automated tests to create or modify

- Create `image-code/tests/test_admin_console_migration.py`
- Create `image-code/tests/test_admin_console.py`
- Create `image-code/tests/test_model_call_recording.py`
- Modify `image-code/tests/test_auth.py`
- Modify `image-code/tests/test_provider_execution.py`
- Modify `image-code/tests/test_provider_resilience.py`
- Modify `image-code/tests/test_text_llm_adapter.py`
- Modify `image-code/tests/test_chat.py`
- Modify `image-code/tests/test_reverse_prompt.py`
- Modify `image-code/tests/test_listing_history_repository.py`
- Create `image-web/src/lib/admin.test.ts`
- Create `image-web/src/pages/AdminOverviewPage.test.ts`
- Create `image-web/src/pages/AdminGenerationsPage.test.ts`
- Modify `image-web/src/components/chat/ChatResultBlock.test.ts`

---

### Task 1: Persistence Foundation and Stable Domain Types

**Files:**
- Create: `image-code/migrations/versions/b8c9d0e1f2a3_admin_console_foundation.py`
- Create: `image-code/src/design_hub/domain/admin.py`
- Modify: `image-code/src/design_hub/infrastructure/db/models.py`
- Create: `image-code/tests/test_admin_console_migration.py`

**Interfaces:**
- Produces: `ModerationStatus`, `ModerationReason`, `ModelCallStatus`, `ModelModality`, `ModelOperation`, `AdminAction`.
- Produces ORM rows: `ModelCallRow`, `AdminAuditLogRow`, and new fields on `AppUser` and `ListingImageRow`.
- Migration revision: `b8c9d0e1f2a3`, down revision: `a7b8c9d0e1f2`.

- [ ] **Step 1: Write the migration and ORM contract tests**

```python
import importlib.util
from pathlib import Path
from types import ModuleType
from typing import Any, cast

import pytest
import sqlalchemy as sa
from alembic.migration import MigrationContext
from alembic.operations import Operations


def _load_migration() -> ModuleType:
    path = (
        Path(__file__).parents[1]
        / "migrations"
        / "versions"
        / "b8c9d0e1f2a3_admin_console_foundation.py"
    )
    spec = importlib.util.spec_from_file_location("admin_console_migration", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def upgraded_connection():
    metadata = sa.MetaData()
    app_user = sa.Table(
        "app_user",
        metadata,
        sa.Column("id", sa.Integer, primary_key=True),
    )
    listing_image = sa.Table(
        "listing_image",
        metadata,
        sa.Column("id", sa.String(32), primary_key=True),
    )
    engine = sa.create_engine("sqlite://")
    with engine.begin() as connection:
        metadata.create_all(connection)
        connection.execute(app_user.insert(), [{"id": 1}, {"id": 2}])
        connection.execute(listing_image.insert(), [{"id": "image-1"}])
        migration = _load_migration()
        cast(Any, migration).op = Operations(MigrationContext.configure(connection))
        migration.upgrade()
        yield connection


def test_admin_console_migration_has_safe_defaults(upgraded_connection):
    users = upgraded_connection.exec_driver_sql(
        "select enabled from app_user"
    ).all()
    images = upgraded_connection.exec_driver_sql(
        "select moderation_status from listing_image"
    ).all()
    assert all(row[0] in (1, True) for row in users)
    assert all(row[0] == "normal" for row in images)


def test_model_call_and_audit_tables_exist(upgraded_connection):
    names = {
        row[0]
        for row in upgraded_connection.exec_driver_sql(
            "select name from sqlite_master where type='table'"
        )
    }
    assert {"model_call", "admin_audit_log"} <= names
```

- [ ] **Step 2: Run the focused migration test and verify failure**

Run:

```bash
cd image-code
uv run pytest -q tests/test_admin_console_migration.py
```

Expected: FAIL because revision `b8c9d0e1f2a3` and the four schema additions do not exist.

- [ ] **Step 3: Add domain enums**

```python
class ModerationStatus(StrEnum):
    NORMAL = "normal"
    BLOCKED = "blocked"


class ModerationReason(StrEnum):
    SEXUAL = "sexual"
    VIOLENCE = "violence"
    ILLEGAL = "illegal"
    INFRINGEMENT = "infringement"
    OTHER = "other"


class ModelCallStatus(StrEnum):
    STARTED = "started"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    UNCERTAIN = "uncertain"
    INTERRUPTED = "interrupted"


class ModelModality(StrEnum):
    IMAGE = "image"
    CHAT = "chat"


class ModelOperation(StrEnum):
    IMAGE_GENERATION = "image_generation"
    IMAGE_EDIT = "image_edit"
    CHAT_COMPLETION = "chat_completion"
    REVERSE_PROMPT = "reverse_prompt"
```

- [ ] **Step 4: Add ORM rows and migration operations**

The migration must:

```python
op.add_column(
    "app_user",
    sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.true()),
)
op.add_column("app_user", sa.Column("disabled_at", sa.DateTime(timezone=True)))
op.add_column("app_user", sa.Column("disabled_by", sa.Integer()))
op.add_column("app_user", sa.Column("disabled_reason", sa.String(500)))
op.add_column(
    "listing_image",
    sa.Column(
        "moderation_status",
        sa.String(16),
        nullable=False,
        server_default="normal",
    ),
)
op.add_column("listing_image", sa.Column("moderation_reason", sa.String(32)))
op.add_column("listing_image", sa.Column("moderation_note", sa.String(500)))
op.add_column("listing_image", sa.Column("moderated_by", sa.Integer()))
op.add_column("listing_image", sa.Column("moderated_at", sa.DateTime(timezone=True)))
```

Create `model_call` with indexed `user_id`, `model`, `operation_type`, `status`, and `started_at`; nullable business references and token fields; `attempt_no >= 1`; and a unique string primary key. Create `admin_audit_log` with indexed actor, target, action, and timestamp. Do not add foreign-key cascades that could erase audit or usage history.

- [ ] **Step 5: Verify migration and model tests**

Run:

```bash
cd image-code
uv run pytest -q tests/test_admin_console_migration.py
uv run alembic upgrade head
uv run alembic check
```

Expected: PASS; Alembic reports no new upgrade operations.

- [ ] **Step 6: Commit**

```bash
git add image-code/migrations/versions/b8c9d0e1f2a3_admin_console_foundation.py \
  image-code/src/design_hub/domain/admin.py \
  image-code/src/design_hub/infrastructure/db/models.py \
  image-code/tests/test_admin_console_migration.py
git commit -m "feat: add admin console persistence foundation" \
  -m "Add safe user and image defaults plus durable model-call and administrator audit records."
```

---

### Task 2: Audited User Status and Live Authorization

**Files:**
- Modify: `image-code/src/design_hub/ports/user_repository.py`
- Modify: `image-code/src/design_hub/infrastructure/db/user_repo.py`
- Modify: `image-code/src/design_hub/application/admin/user_admin_service.py`
- Modify: `image-code/src/design_hub/interface/api/deps.py`
- Modify: `image-code/src/design_hub/interface/api/routes/users.py`
- Modify: `image-code/src/design_hub/interface/auth_schemas.py`
- Modify: `image-code/src/design_hub/interface/api/asgi.py`
- Modify: `image-code/tests/test_auth.py`
- Create: `image-code/tests/test_admin_console.py`

**Interfaces:**
- `UserAccount.enabled: bool`, `disabled_at: datetime | None`, `disabled_reason: str | None`.
- `UserAdminService.set_status(actor_id: int, user_id: int, enabled: bool, reason: str)`.
- `CurrentManagerDep = Annotated[AuthUser, Depends(require_role(Role.MANAGER))]`.
- `UserStatusUpdate(enabled: bool, reason: str)` with stripped `reason`, 1–500 characters when disabling.

- [ ] **Step 1: Add failing service and HTTP tests**

```python
async def test_manager_cannot_disable_self(user_admin_service):
    with pytest.raises(DomainError, match="不能停用自己"):
        await user_admin_service.set_status(
            actor_id=1, user_id=1, enabled=False, reason="test"
        )


async def test_disabled_token_is_rejected_on_next_request(client, user_token, disable_user):
    await disable_user(reason="合规处置")
    response = await client.get("/me", headers={"Authorization": f"Bearer {user_token}"})
    assert response.status_code == 401
    assert response.json()["error"] == "unauthenticated"


async def test_last_enabled_manager_cannot_be_disabled(manager_client, manager_id):
    response = await manager_client.put(
        f"/admin/users/{manager_id}/status",
        json={"enabled": False, "reason": "test"},
    )
    assert response.status_code == 409
```

- [ ] **Step 2: Run tests and verify failure**

Run:

```bash
cd image-code
uv run pytest -q tests/test_auth.py tests/test_admin_console.py -k "disabled or manager"
```

Expected: FAIL because `enabled`, current-user database refresh, and status endpoint do not exist.

- [ ] **Step 3: Extend the user port and repository**

Use these signatures:

```python
class UserRepository(ABC):
    async def set_status_with_audit(
        self,
        *,
        actor_id: int,
        user_id: int,
        enabled: bool,
        reason: str,
    ) -> UserAccount: ...

    async def set_role_with_audit(
        self,
        *,
        actor_id: int,
        user_id: int,
        role: Role,
    ) -> UserAccount: ...
```

Both methods open one `session.begin()` transaction, lock the target row, enforce self/last-manager rules, update the row, and insert `AdminAuditLogRow`.

- [ ] **Step 4: Refresh the current user from the database**

`get_current_user` and `get_current_user_sse` must:

```python
claims = token_service.verify(token)
account = await user_repository.get_by_id(int(claims.user_id))
if account is None or not account.enabled:
    raise AuthenticationError("账号已停用或不存在")
return AuthUser(
    user_id=str(account.id),
    name=account.name,
    role=account.role,
    dept=None,
)
```

Renew JWT only after the current database account passes. Use the database role, not the role embedded in the old token.

- [ ] **Step 5: Add audited role/status routes**

```python
@router.put("/users/{user_id}/status", response_model=UserOut)
async def set_user_status(
    user_id: int,
    body: UserStatusUpdate,
    manager: CurrentManagerDep,
    svc: UserAdminServiceDep,
) -> UserOut:
    return UserOut.of(
        await svc.set_status(
            actor_id=int(manager.user_id),
            user_id=user_id,
            enabled=body.enabled,
            reason=body.reason,
        )
    )
```

Update the role route to pass the current manager ID and write audit in the same transaction.

- [ ] **Step 6: Run focused tests**

Run:

```bash
cd image-code
uv run pytest -q tests/test_auth.py tests/test_admin_console.py -k "disabled or role or manager"
uv run mypy src
uv run ruff check src tests
```

Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add image-code/src/design_hub/ports/user_repository.py \
  image-code/src/design_hub/infrastructure/db/user_repo.py \
  image-code/src/design_hub/application/admin/user_admin_service.py \
  image-code/src/design_hub/interface/api/deps.py \
  image-code/src/design_hub/interface/api/routes/users.py \
  image-code/src/design_hub/interface/auth_schemas.py \
  image-code/src/design_hub/interface/api/asgi.py \
  image-code/tests/test_auth.py image-code/tests/test_admin_console.py
git commit -m "feat: add audited user account controls" \
  -m "Apply current database roles and enabled state to every authenticated request while protecting the active manager account."
```

---

### Task 3: Durable Model-Call Recorder and GPT Image Attempt Counting

**Files:**
- Create: `image-code/src/design_hub/ports/model_calls.py`
- Create: `image-code/src/design_hub/infrastructure/db/model_call_repo.py`
- Modify: `image-code/src/design_hub/ports/model_provider.py`
- Modify: `image-code/src/design_hub/ports/provider_execution.py`
- Modify: `image-code/src/design_hub/infrastructure/providers/mock.py`
- Modify: `image-code/src/design_hub/infrastructure/providers/openai_compat.py`
- Modify: `image-code/src/design_hub/infrastructure/providers/apinebula_async.py`
- Modify: `image-code/src/design_hub/infrastructure/providers/execution.py`
- Modify: `image-code/src/design_hub/application/tasking/worker.py`
- Modify: `image-code/src/design_hub/composition.py`
- Create: `image-code/tests/test_model_call_recording.py`
- Modify: `image-code/tests/test_provider_execution.py`
- Modify: `image-code/tests/test_provider_resilience.py`

**Interfaces:**

```python
@dataclass(frozen=True)
class ModelCallContext:
    user_id: str
    operation: ModelOperation
    job_id: str | None = None
    generation_item_id: str | None = None
    chat_session_id: str | None = None


@dataclass(frozen=True)
class ModelUsage:
    input_tokens: int | None = None
    output_tokens: int | None = None
    total_tokens: int | None = None
    input_text_tokens: int | None = None
    input_image_tokens: int | None = None
    output_image_tokens: int | None = None


class ModelCallRecorder(Protocol):
    async def start(
        self,
        *,
        context: ModelCallContext,
        provider: str,
        model: str,
        attempt_no: int,
    ) -> str: ...
    async def succeed(
        self,
        call_id: str,
        *,
        usage: ModelUsage,
        provider_request_id: str | None,
        platform_cost: Decimal | None,
        diagnostic_code: str | None = None,
    ) -> None: ...
    async def fail(self, call_id: str, *, code: str, detail: str) -> None: ...
    async def uncertain(self, call_id: str, *, detail: str) -> None: ...
    async def interrupt(self, call_id: str) -> None: ...
```

- [ ] **Step 1: Write failing recorder and retry-count tests**

```python
async def test_each_image_retry_is_recorded(fake_recorder, retrying_image_client, provider):
    await provider.generate(
        context=ModelCallContext(
            user_id="7",
            operation=ModelOperation.IMAGE_EDIT,
            job_id="job-1",
            generation_item_id="item-1",
        ),
        prompt="edit",
        negative_prompt="",
        reference_images=[reference_image()],
        size=(1024, 1024),
        n=1,
        seed=1,
    )
    assert [call.attempt_no for call in fake_recorder.started] == [1, 2]
    assert fake_recorder.failed[0].code == "provider_timeout"
    assert len(fake_recorder.succeeded) == 1


async def test_async_poll_is_not_counted(fake_recorder, async_provider):
    await async_provider.submit_task(request(), operation_id="op", context=context())
    await async_provider.resume_task("task-1", request())
    assert len(fake_recorder.started) == 1
```

- [ ] **Step 2: Run tests and verify failure**

Run:

```bash
cd image-code
uv run pytest -q tests/test_model_call_recording.py tests/test_provider_resilience.py
```

Expected: FAIL because no recorder or explicit call context exists.

- [ ] **Step 3: Implement the SQLAlchemy recorder**

`start()` inserts and commits a `started` row before network I/O. Finalizers update exactly one row and reject illegal second finalization. Error detail is capped at 500 characters. Derive latency from database `started_at` and current UTC time.

- [ ] **Step 4: Make image call context explicit**

Add `context: ModelCallContext` to `ProviderRequest` and to image provider generation/submission signatures. Build it in `GenerationWorker`:

```python
context=ModelCallContext(
    user_id=work.user_id,
    operation=ModelOperation(work.spec.operation_type.value),
    job_id=work.job_id,
    generation_item_id=work.spec.item_id,
)
```

Mock providers accept the context and perform no recording because they make no upstream request.

- [ ] **Step 5: Record each synchronous GPT Image attempt**

Inside the retry loop, immediately before `_generate()` or `_edit()`:

```python
call_id = await self._recorder.start(
    context=context,
    provider=self.name.value,
    model=self._model,
    attempt_no=attempt + 1,
)
```

On an HTTP response, parse `usage` through one strict helper and call `succeed`. On timeout/transport/5xx call `fail`; on `SubmissionUncertain` call `uncertain`; on cancellation call `interrupt` and re-raise. Do not instrument `_download_external_image`.

- [ ] **Step 6: Record only async submit POSTs**

Wrap every `_post_json` submit attempt with the same recorder. Do not add recorder calls to `_poll`, `_get`, or `_download_and_store`.

- [ ] **Step 7: Wire the recorder in the composition root**

Create one `SqlAlchemyModelCallRecorder(session_factory)` after the database session factory exists. Pass it to real image providers and the real text provider. Do not create a no-op compatibility adapter for real providers.

- [ ] **Step 8: Run focused tests and static gates**

Run:

```bash
cd image-code
uv run pytest -q tests/test_model_call_recording.py \
  tests/test_provider_execution.py tests/test_provider_resilience.py
uv run mypy src
uv run ruff check src tests
```

Expected: PASS.

- [ ] **Step 9: Commit**

```bash
git add image-code/src/design_hub/ports/model_calls.py \
  image-code/src/design_hub/infrastructure/db/model_call_repo.py \
  image-code/src/design_hub/ports/model_provider.py \
  image-code/src/design_hub/ports/provider_execution.py \
  image-code/src/design_hub/infrastructure/providers/mock.py \
  image-code/src/design_hub/infrastructure/providers/openai_compat.py \
  image-code/src/design_hub/infrastructure/providers/apinebula_async.py \
  image-code/src/design_hub/infrastructure/providers/execution.py \
  image-code/src/design_hub/application/tasking/worker.py \
  image-code/src/design_hub/composition.py \
  image-code/tests/test_model_call_recording.py \
  image-code/tests/test_provider_execution.py \
  image-code/tests/test_provider_resilience.py
git commit -m "feat: record GPT Image API attempts" \
  -m "Persist every real generation or edit submission, including retries, while excluding polling and result downloads."
```

---

### Task 4: Doubao Chat Usage and Per-Round Call Accounting

**Files:**
- Modify: `image-code/src/design_hub/ports/text_llm.py`
- Modify: `image-code/src/design_hub/infrastructure/providers/mock_text.py`
- Modify: `image-code/src/design_hub/infrastructure/providers/openai_compat_text.py`
- Modify: `image-code/src/design_hub/application/chat/orchestrator.py`
- Modify: `image-code/src/design_hub/application/image_prompts/reverse_prompt.py`
- Modify: `image-code/src/design_hub/composition.py`
- Modify: `image-code/tests/test_text_llm_adapter.py`
- Modify: `image-code/tests/test_chat.py`
- Modify: `image-code/tests/test_reverse_prompt.py`
- Modify: `image-code/tests/test_chat_harness.py`

**Interfaces:**
- `TextLLMPort.complete(*, context: ModelCallContext, messages: list[ChatMessage], tools: list[ToolSpec])`.
- Every orchestrator LLM round creates a fresh call using the same user/session context.
- Standalone reverse prompt uses `ModelOperation.REVERSE_PROMPT` and no chat session.

- [ ] **Step 1: Write failing streaming usage tests**

```python
async def test_stream_usage_is_recorded_when_choices_are_empty(fake_recorder):
    provider = provider_with_sse(
        [
            'data: {"choices":[{"delta":{"content":"好"}}]}',
            'data: {"choices":[],"usage":{"prompt_tokens":21,'
            '"completion_tokens":8,"total_tokens":29}}',
            "data: [DONE]",
        ],
        recorder=fake_recorder,
    )
    chunks = [
        chunk
        async for chunk in provider.complete(
            context=chat_context(),
            messages=[ChatMessage(role="user", content="你好")],
            tools=[],
        )
    ]
    assert [chunk.text for chunk in chunks if isinstance(chunk, TextChunk)] == ["好"]
    assert fake_recorder.succeeded[0].usage.total_tokens == 29


async def test_each_tool_loop_round_records_one_chat_call(chat_orchestrator, fake_recorder):
    await collect(chat_orchestrator.message(user(), request_with_tool_round()))
    assert [call.context.operation for call in fake_recorder.started] == [
        ModelOperation.CHAT_COMPLETION,
        ModelOperation.CHAT_COMPLETION,
    ]
```

- [ ] **Step 2: Run focused tests and verify failure**

Run:

```bash
cd image-code
uv run pytest -q tests/test_text_llm_adapter.py tests/test_chat.py \
  tests/test_reverse_prompt.py -k "usage or call"
```

Expected: FAIL because the provider drops the empty-choices usage chunk and has no context.

- [ ] **Step 3: Send the usage request option**

The text payload must include:

```python
"stream": True,
"stream_options": {"include_usage": True},
```

Parse each SSE body once. Handle `usage` before looking for `choices`; then parse text/tool deltas as before.

- [ ] **Step 4: Finalize each Chat call**

Start one call before opening the HTTP stream. On `[DONE]`, finalize success with the upstream usage object. If content ends without usage, finalize success with missing token fields and `diagnostic_code="usage_missing"`; surface that diagnostic in admin data without estimating tokens. On HTTP error, interruption, or cancellation, finalize the corresponding status and re-raise existing domain errors.

- [ ] **Step 5: Pass explicit context from every caller**

Chat:

```python
ModelCallContext(
    user_id=user.user_id,
    operation=ModelOperation.CHAT_COMPLETION,
    chat_session_id=session_id,
)
```

Reverse prompt:

```python
ModelCallContext(
    user_id=user_id,
    operation=ModelOperation.REVERSE_PROMPT,
)
```

Every `_to_llm_messages` tool loop and the post-generation closing round must pass context. Mock text calls do not write model-call rows.

- [ ] **Step 6: Run focused tests and static gates**

Run:

```bash
cd image-code
uv run pytest -q tests/test_text_llm_adapter.py tests/test_chat.py \
  tests/test_reverse_prompt.py tests/test_chat_harness.py
uv run mypy src
uv run ruff check src tests
```

Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add image-code/src/design_hub/ports/text_llm.py \
  image-code/src/design_hub/infrastructure/providers/mock_text.py \
  image-code/src/design_hub/infrastructure/providers/openai_compat_text.py \
  image-code/src/design_hub/application/chat/orchestrator.py \
  image-code/src/design_hub/application/image_prompts/reverse_prompt.py \
  image-code/src/design_hub/composition.py \
  image-code/tests/test_text_llm_adapter.py image-code/tests/test_chat.py \
  image-code/tests/test_reverse_prompt.py image-code/tests/test_chat_harness.py
git commit -m "feat: record Doubao Chat token usage" \
  -m "Capture every live Chat round and persist authoritative streaming input, output, and total token usage."
```

---

### Task 5: Admin Query Service, Aggregates, and Paginated APIs

**Files:**
- Create: `image-code/src/design_hub/ports/admin_console.py`
- Create: `image-code/src/design_hub/infrastructure/db/admin_console_repo.py`
- Create: `image-code/src/design_hub/application/admin/admin_console_service.py`
- Create: `image-code/src/design_hub/interface/admin_console_schemas.py`
- Create: `image-code/src/design_hub/interface/api/routes/admin_console.py`
- Modify: `image-code/src/design_hub/interface/api/admin_deps.py`
- Modify: `image-code/src/design_hub/interface/api/asgi.py`
- Modify: `image-code/tests/test_admin_console.py`

**Interfaces:**
- `Page[T](items: tuple[T, ...], total: int, limit: int, offset: int)`.
- Date ranges use UTC inclusive `start` and exclusive `end`, with `start < end` and maximum 366 days.
- Stable ordering: timestamp descending, primary key descending.

- [ ] **Step 1: Write failing manager, aggregation, and pagination tests**

```python
async def test_non_manager_cannot_read_admin_overview(user_client):
    response = await user_client.get("/admin/overview")
    assert response.status_code == 403


async def test_model_call_summary_counts_retries_but_not_historical_jobs(manager_client, seeded_calls):
    response = await manager_client.get(
        "/admin/model-calls/summary?start=2026-07-01T00:00:00Z"
        "&end=2026-08-01T00:00:00Z"
    )
    assert response.status_code == 200
    image = next(row for row in response.json()["models"] if row["model"] == "gpt-image-2")
    assert image["calls"] == 3
    assert image["retries"] == 1


async def test_admin_images_use_stable_pagination(manager_client, seeded_images):
    first = (await manager_client.get("/admin/images?limit=2&offset=0")).json()
    second = (await manager_client.get("/admin/images?limit=2&offset=2")).json()
    assert set(item["image_id"] for item in first["items"]).isdisjoint(
        item["image_id"] for item in second["items"]
    )
```

- [ ] **Step 2: Run focused tests and verify failure**

Run:

```bash
cd image-code
uv run pytest -q tests/test_admin_console.py -k "overview or summary or pagination"
```

Expected: FAIL because the admin console routes and query repository do not exist.

- [ ] **Step 3: Define read models and filters**

Create explicit dataclasses for:

- `AdminOverview`;
- `AdminUserSummary`, `AdminUserDetail`;
- `AdminJobSummary`, `AdminJobDetail`;
- `AdminImageSummary`;
- `ModelCallSummary`, `ModelCallDetail`;
- `AdminAuditEntry`.

Do not return ORM objects from ports or application services.

- [ ] **Step 4: Implement aggregate and paginated SQL**

Use SQL aggregate queries and bounded joins, not Python loops over all records. User “last activity” is the greatest of latest job, chat-session update, and model-call start. Signed URLs are added at the interface boundary only for the current page.

Stale `started` rows older than the model-specific maximum wall clock are serialized as `uncertain` without mutating the stored row.

- [ ] **Step 5: Add HTTP schemas and routes**

Each list response has:

```python
class PageOut[T](BaseModel):
    items: list[T]
    total: int
    limit: int
    offset: int
```

Expose the exact endpoints from the approved design. Reuse `CurrentManagerDep` to make actor identity available and keep include-level manager enforcement.

- [ ] **Step 6: Run tests and backend gates**

Run:

```bash
cd image-code
uv run pytest -q tests/test_admin_console.py
uv run mypy src
uv run ruff check src tests
```

Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add image-code/src/design_hub/ports/admin_console.py \
  image-code/src/design_hub/infrastructure/db/admin_console_repo.py \
  image-code/src/design_hub/application/admin/admin_console_service.py \
  image-code/src/design_hub/interface/admin_console_schemas.py \
  image-code/src/design_hub/interface/api/routes/admin_console.py \
  image-code/src/design_hub/interface/api/admin_deps.py \
  image-code/src/design_hub/interface/api/asgi.py \
  image-code/tests/test_admin_console.py
git commit -m "feat: add manager console APIs" \
  -m "Expose bounded cross-user overview, generation, model-usage, and audit queries behind manager authorization."
```

---

### Task 6: Reversible Image Moderation and User-Side Enforcement

**Files:**
- Modify: `image-code/src/design_hub/ports/admin_console.py`
- Modify: `image-code/src/design_hub/infrastructure/db/admin_console_repo.py`
- Modify: `image-code/src/design_hub/application/admin/admin_console_service.py`
- Modify: `image-code/src/design_hub/interface/admin_console_schemas.py`
- Modify: `image-code/src/design_hub/interface/api/routes/admin_console.py`
- Modify: `image-code/src/design_hub/ports/listing_query.py`
- Modify: `image-code/src/design_hub/infrastructure/db/listing_query_repo.py`
- Modify: `image-code/src/design_hub/interface/listing_history_schemas.py`
- Modify: `image-code/tests/test_admin_console.py`
- Modify: `image-code/tests/test_listing_history_repository.py`
- Modify: `image-code/tests/test_reverse_prompt.py`
- Modify: `image-code/tests/test_background_replacement.py`

**Interfaces:**
- `AdminConsoleService.set_image_moderation(actor_id, image_id, status, reason, note)`.
- Ordinary `ListingJobImageView.available: bool`.
- Ordinary `ListingImageOut.url: str | None`, `available: bool`; no moderation reason.
- Admin image output includes status, reason, note, actor, and timestamp.

- [ ] **Step 1: Write failing end-to-end moderation tests**

```python
async def test_blocked_image_is_unavailable_everywhere(
    manager_client, user_client, image_id, job_id, image_key
):
    blocked = await manager_client.put(
        f"/admin/images/{image_id}/moderation",
        json={
            "status": "blocked",
            "reason": "illegal",
            "note": "manual review",
        },
    )
    assert blocked.status_code == 200

    history = await user_client.get(f"/listing/jobs/{job_id}")
    image = next(row for row in history.json()["images"] if row["image_key"] == image_key)
    assert image == {
        **image,
        "url": None,
        "available": False,
    }

    reverse = await user_client.post(
        "/image-prompts/reverse",
        json={"source": {"kind": "generated", "image_key": image_key}},
    )
    assert reverse.status_code == 404


async def test_repeated_block_is_conflict(manager_client, image_id):
    payload = {"status": "blocked", "reason": "other", "note": ""}
    assert (await manager_client.put(
        f"/admin/images/{image_id}/moderation", json=payload
    )).status_code == 200
    assert (await manager_client.put(
        f"/admin/images/{image_id}/moderation", json=payload
    )).status_code == 409
```

- [ ] **Step 2: Run focused tests and verify failure**

Run:

```bash
cd image-code
uv run pytest -q tests/test_admin_console.py \
  tests/test_listing_history_repository.py tests/test_reverse_prompt.py \
  tests/test_background_replacement.py -k "blocked or moderation"
```

Expected: FAIL because no moderation transition or enforcement exists.

- [ ] **Step 3: Add one transactional moderation mutation**

Lock `ListingImageRow`, reject a no-op transition, require a reason for `blocked`, clear reason/note on restore, update actor/time, and insert `AdminAuditLogRow` in the same transaction.

- [ ] **Step 4: Enforce moderation in all source resolution**

Add `ListingImageRow.moderation_status == "normal"` to `resolve_generated_image_source`. Propagate availability into history summaries/details. Do not expose `moderation_status` or reason to ordinary schemas; serialize only `available` and a nullable URL.

If an edit-chain source image becomes blocked, its `source_image_url` is `None` and it cannot be selected for a new operation.

- [ ] **Step 5: Verify manager-only preview**

Admin image/job detail uses the admin repository and may sign blocked image keys. Ordinary history/chat code never calls that branch.

- [ ] **Step 6: Run focused and static tests**

Run:

```bash
cd image-code
uv run pytest -q tests/test_admin_console.py \
  tests/test_listing_history_repository.py tests/test_reverse_prompt.py \
  tests/test_background_replacement.py tests/test_chat.py
uv run mypy src
uv run ruff check src tests
```

Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add image-code/src/design_hub/ports/admin_console.py \
  image-code/src/design_hub/infrastructure/db/admin_console_repo.py \
  image-code/src/design_hub/application/admin/admin_console_service.py \
  image-code/src/design_hub/interface/admin_console_schemas.py \
  image-code/src/design_hub/interface/api/routes/admin_console.py \
  image-code/src/design_hub/ports/listing_query.py \
  image-code/src/design_hub/infrastructure/db/listing_query_repo.py \
  image-code/src/design_hub/interface/listing_history_schemas.py \
  image-code/tests/test_admin_console.py \
  image-code/tests/test_listing_history_repository.py \
  image-code/tests/test_reverse_prompt.py \
  image-code/tests/test_background_replacement.py
git commit -m "feat: add reversible image moderation" \
  -m "Let managers block and restore generated images while enforcing unavailability across every ordinary-user image workflow."
```

---

### Task 7: Audit Existing Model Configuration Mutations

**Files:**
- Modify: `image-code/src/design_hub/application/admin/model_config_service.py`
- Modify: `image-code/src/design_hub/ports/model_config_repository.py`
- Modify: `image-code/src/design_hub/infrastructure/db/model_config_repo.py`
- Modify: `image-code/src/design_hub/interface/api/routes/admin.py`
- Modify: `image-code/tests/test_model_config.py`
- Modify: `image-code/tests/test_admin_console.py`

**Interfaces:**
- Every model-config mutation receives `actor_id: int`.
- Repository mutation and `AdminAuditLogRow` share one transaction.

- [ ] **Step 1: Write failing audit atomicity tests**

```python
async def test_model_update_creates_one_safe_audit_row(manager_client, audit_repo):
    response = await manager_client.put(
        "/admin/models/gpt-image-2",
        json={"enabled": False},
    )
    assert response.status_code == 200
    entry = (await audit_repo.list(action="model.update"))[0]
    assert entry.target_id == "gpt-image-2"
    assert "api_key" not in json.dumps(entry.after)


async def test_model_update_rolls_back_when_audit_insert_fails(
    model_repo_with_failed_audit
):
    with pytest.raises(RuntimeError):
        await model_repo_with_failed_audit.update_with_audit(
            actor_id=1,
            name="gpt-image-2",
            enabled=False,
        )
    assert (await model_repo_with_failed_audit.get("gpt-image-2")).enabled is True
```

- [ ] **Step 2: Run focused tests and verify failure**

Run:

```bash
cd image-code
uv run pytest -q tests/test_model_config.py tests/test_admin_console.py -k "audit"
```

Expected: FAIL because model writes do not know the actor or audit table.

- [ ] **Step 3: Refactor model mutations to audited repository methods**

Pass `actor_id` from `CurrentManagerDep` through service methods. Sanitize before/after snapshots to keep only name, unit cost, enabled state, provider type, base URL, model ID, API-key environment variable name, and default state.

- [ ] **Step 4: Run focused tests**

Run:

```bash
cd image-code
uv run pytest -q tests/test_model_config.py tests/test_admin_console.py
uv run mypy src
uv run ruff check src tests
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add image-code/src/design_hub/application/admin/model_config_service.py \
  image-code/src/design_hub/ports/model_config_repository.py \
  image-code/src/design_hub/infrastructure/db/model_config_repo.py \
  image-code/src/design_hub/interface/api/routes/admin.py \
  image-code/tests/test_model_config.py image-code/tests/test_admin_console.py
git commit -m "feat: audit model configuration changes" \
  -m "Make every manager model mutation atomic with a secret-safe administrator audit record."
```

---

### Task 8: OpenAPI Contract and Admin Frontend Shell

**Files:**
- Modify: `image-web/openapi.json`
- Modify: `image-web/src/api/schema.d.ts`
- Modify: `image-web/src/api/admin.ts`
- Modify: `image-web/src/api/users.ts`
- Create: `image-web/src/components/admin/AdminLayout.tsx`
- Create: `image-web/src/components/admin/AdminPagination.tsx`
- Create: `image-web/src/components/admin/AdminMetricCard.tsx`
- Create: `image-web/src/pages/AdminOverviewPage.tsx`
- Create: `image-web/src/pages/AdminOverviewPage.test.ts`
- Modify: `image-web/src/components/layout/navigation.ts`
- Modify: `image-web/src/components/layout/navigation.test.ts`
- Modify: `image-web/src/App.tsx`
- Create: `image-web/src/lib/admin.test.ts`

**Interfaces:**
- One ordinary account-menu item: `{ to: "/admin", label: "管理后台" }`.
- This task registers working overview, users, and models routes; Task 9 adds generations, usage, and audit after their pages exist.
- TanStack query keys include normalized filter objects.

- [ ] **Step 1: Export and generate the API contract**

Run:

```bash
cd image-code
uv run python -c 'import json; from design_hub.interface.api.asgi import app; print(json.dumps(app.openapi(), ensure_ascii=False))' > ../image-web/openapi.json
cd ../image-web
npm run gen:api
```

Expected: `schema.d.ts` contains `/admin/overview`, `/admin/images`, `/admin/model-calls`, and the paginated `/admin/users` response.

- [ ] **Step 2: Write failing navigation and filter serialization tests**

```ts
expect(getAccountNavItems('管理者').map(({ label, to }) => ({ label, to }))).toEqual([
  { label: '管理后台', to: '/admin' },
])

expect(adminSearchParams({ limit: 20, offset: 0, status: 'failed' }).toString()).toBe(
  'limit=20&offset=0&status=failed',
)

render(<AdminOverviewPage />, { wrapper: adminQueryWrapper(summaryFixture) })
expect(screen.getByText('GPT Image 2 调用')).toBeInTheDocument()
expect(screen.getByText('12')).toBeInTheDocument()
expect(screen.getByText('豆包总 Token')).toBeInTheDocument()
```

- [ ] **Step 3: Run tests and verify failure**

Run:

```bash
cd image-web
npm test -- src/components/layout/navigation.test.ts src/lib/admin.test.ts \
  src/pages/AdminOverviewPage.test.ts
```

Expected: FAIL because the unified route and admin filter helper do not exist.

- [ ] **Step 4: Implement typed API hooks**

Add hooks for:

- overview;
- paginated users and user status;
- jobs and job detail;
- images and moderation mutation;
- model-call summary and details;
- audit logs.

Every mutation invalidates only the relevant admin query roots plus affected ordinary history queries for the current manager account.

- [ ] **Step 5: Add the admin shell**

`AdminLayout` renders the existing `AppShell`, a compact sidebar, and `<Outlet />`. Use `NavLink` active state. Do not add another UI framework or chart dependency.

- [ ] **Step 6: Build the overview and register only existing pages**

Use metric cards, a CSS/SVG trend strip only when at least two buckets exist, a recent-failures table, and recent-blocked thumbnails. Clearly label call-data start time and “平台核算成本”.

```tsx
<Route
  path="admin"
  element={
    <RoleRoute allow={[ROLE_MANAGER]}>
      <AdminLayout />
    </RoleRoute>
  }
>
  <Route index element={<AdminOverviewPage />} />
  <Route path="users" element={<AdminUsersPage />} />
  <Route path="models" element={<AdminModelsPage />} />
</Route>
```

Task 9 extends this nested route only after the remaining page components exist.

- [ ] **Step 7: Run focused frontend tests and typecheck**

Run:

```bash
cd image-web
npm test -- src/components/layout/navigation.test.ts src/lib/admin.test.ts \
  src/pages/AdminOverviewPage.test.ts
npm run typecheck
```

Expected: PASS.

- [ ] **Step 8: Commit**

```bash
git add image-web/openapi.json image-web/src/api/schema.d.ts \
  image-web/src/api/admin.ts image-web/src/api/users.ts \
  image-web/src/components/admin/AdminLayout.tsx \
  image-web/src/components/admin/AdminPagination.tsx \
  image-web/src/components/admin/AdminMetricCard.tsx \
  image-web/src/pages/AdminOverviewPage.tsx \
  image-web/src/pages/AdminOverviewPage.test.ts \
  image-web/src/components/layout/navigation.ts \
  image-web/src/components/layout/navigation.test.ts \
  image-web/src/App.tsx image-web/src/lib/admin.test.ts
git commit -m "feat: add unified admin console shell" \
  -m "Replace scattered manager links with one typed, nested administration workspace and shared pagination controls."
```

---

### Task 9: Admin Overview, Users, Generations, Usage, and Audit Pages

**Files:**
- Create: `image-web/src/pages/AdminGenerationsPage.tsx`
- Create: `image-web/src/pages/AdminGenerationDetailPage.tsx`
- Create: `image-web/src/pages/AdminUsagePage.tsx`
- Create: `image-web/src/pages/AdminAuditPage.tsx`
- Create: `image-web/src/components/admin/ModerationDialog.tsx`
- Modify: `image-web/src/pages/AdminUsersPage.tsx`
- Modify: `image-web/src/pages/AdminModelsPage.tsx`
- Create: `image-web/src/pages/AdminGenerationsPage.test.ts`

**Interfaces:**
- Filters live in URL query parameters.
- `ModerationDialog` requires a reason when blocking and sends an empty reason/note when restoring.
- All pages implement loading, error, empty, and populated states.

- [ ] **Step 1: Write failing moderation interaction and route tests**

```tsx
render(<ModerationDialog image={normalImage} onSubmit={submit} />)
await user.click(screen.getByRole('button', { name: '确认屏蔽' }))
expect(submit).not.toHaveBeenCalled()
await user.selectOptions(screen.getByLabelText('违规原因'), 'illegal')
await user.click(screen.getByRole('button', { name: '确认屏蔽' }))
expect(submit).toHaveBeenCalledWith({
  status: 'blocked',
  reason: 'illegal',
  note: '',
})

renderAdminAt('/admin/generations')
expect(await screen.findByRole('heading', { name: '出图管理' })).toBeInTheDocument()
```

- [ ] **Step 2: Run tests and verify failure**

Run:

```bash
cd image-web
npm test -- src/pages/AdminGenerationsPage.test.ts
```

Expected: FAIL because pages and moderation dialog do not exist.

- [ ] **Step 3: Upgrade users and models into the shell**

Users use server pagination/search/status filters, show per-user aggregates, and expose role/status actions. Disabling requires a reason; current manager and the last active manager controls are disabled in the UI while the backend remains authoritative.

Models keep existing functionality and content; remove duplicate page-level “仅管理者可见” copy because the shell already establishes context.

- [ ] **Step 4: Build generation list/grid and detail**

Provide list/grid toggle, bounded filters, lazy thumbnails, task/user/call links, and on-demand detail. Blocked thumbnails carry an admin-only badge. The moderation dialog supports block and restore; no batch action.

- [ ] **Step 5: Build usage and audit pages and register their routes**

Usage shows model summaries first and paginated calls below. GPT Image emphasizes call count/retry/success; Doubao emphasizes calls and input/output/total tokens. Audit renders safe before/after changes and reasons without raw secrets.

Extend the existing `/admin` nested route with:

```tsx
<Route path="generations" element={<AdminGenerationsPage />} />
<Route path="generations/:jobId" element={<AdminGenerationDetailPage />} />
<Route path="usage" element={<AdminUsagePage />} />
<Route path="audit" element={<AdminAuditPage />} />
```

- [ ] **Step 6: Run page tests, lint, and typecheck**

Run:

```bash
cd image-web
npm test -- src/pages/AdminGenerationsPage.test.ts
npm run lint
npm run typecheck
```

Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add image-web/src/pages/AdminGenerationsPage.tsx \
  image-web/src/pages/AdminGenerationDetailPage.tsx \
  image-web/src/pages/AdminUsagePage.tsx \
  image-web/src/pages/AdminAuditPage.tsx \
  image-web/src/components/admin/ModerationDialog.tsx \
  image-web/src/pages/AdminUsersPage.tsx \
  image-web/src/pages/AdminModelsPage.tsx \
  image-web/src/pages/AdminGenerationsPage.test.ts \
  image-web/src/App.tsx
git commit -m "feat: build admin operations pages" \
  -m "Add manager overview, user controls, generation review, model usage, moderation, and audit views."
```

---

### Task 10: Ordinary-User Blocked Image States

**Files:**
- Modify: `image-web/src/pages/HistoryPage.tsx`
- Modify: `image-web/src/pages/HistoryDetailPage.tsx`
- Modify: `image-web/src/components/listing/ResultGallery.tsx`
- Modify: `image-web/src/components/chat/ChatResultBlock.tsx`
- Modify: `image-web/src/lib/listing.ts`
- Modify: `image-web/src/components/chat/ChatResultBlock.test.ts`
- Modify: `image-web/src/lib/listing.test.ts`

**Interfaces:**
- Ordinary API exposes only `available: false` and `url: null`.
- User-facing copy: `该图片暂不可用`.
- No moderation status, reason, note, actor, or admin terminology appears.

- [ ] **Step 1: Write failing blocked-state tests**

```tsx
render(
  <ChatResultBlock
    slots={[{ url: null, imageKey: 'key', unavailable: true }]}
    done={1}
    total={1}
    onPreview={vi.fn()}
    onEdit={vi.fn()}
    onBackground={vi.fn()}
    onReversePrompt={vi.fn()}
  />,
)
expect(screen.getByText('该图片暂不可用')).toBeInTheDocument()
expect(screen.queryByRole('button', { name: /下载/ })).not.toBeInTheDocument()
expect(screen.queryByRole('button', { name: /继续编辑/ })).not.toBeInTheDocument()
```

- [ ] **Step 2: Run tests and verify failure**

Run:

```bash
cd image-web
npm test -- src/components/chat/ChatResultBlock.test.ts src/lib/listing.test.ts
```

Expected: FAIL because result slots do not represent blocked availability.

- [ ] **Step 3: Add the neutral unavailable state**

Extend frontend result types with `unavailable?: boolean`. Render a neutral placeholder instead of `<img>`. Do not pass an image key into edit/background/reverse-prompt actions when unavailable. Exclude unavailable slots from “下载全部”.

- [ ] **Step 4: Cover history list/detail**

If a job has no available first image, show the neutral unavailable thumbnail state rather than a broken image. Detail rows preserve the slot and cost metadata but hide all image actions.

- [ ] **Step 5: Run tests and frontend gates**

Run:

```bash
cd image-web
npm test -- src/components/chat/ChatResultBlock.test.ts src/lib/listing.test.ts
npm run lint
npm run typecheck
```

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add image-web/src/pages/HistoryPage.tsx \
  image-web/src/pages/HistoryDetailPage.tsx \
  image-web/src/components/listing/ResultGallery.tsx \
  image-web/src/components/chat/ChatResultBlock.tsx \
  image-web/src/lib/listing.ts \
  image-web/src/components/chat/ChatResultBlock.test.ts \
  image-web/src/lib/listing.test.ts
git commit -m "feat: enforce blocked image states in user UI" \
  -m "Remove preview and downstream image actions while showing only a neutral unavailable message to ordinary users."
```

---

### Task 11: Full Verification and Release Readiness

**Files:**
- Modify only if verification exposes a defect in files already owned by Tasks 1–10.
- Update: `image-code/docs/superpowers/specs/2026-07-30-admin-console-design.md` status from `已确认，待实现` to `已实现，待 QA 验证`.
- Create: `image-issues/ISSUE-0070-管理后台验收.md` using `_TEMPLATE.md`, status `待复现`, owner `QA`, with the exact acceptance matrix below.

**Interfaces:**
- No new product behavior. This task verifies the integrated deliverable and hands independent QA a bounded checklist.

- [ ] **Step 1: Run the full backend gate**

Run:

```bash
cd image-code
uv sync --all-groups
uv run pytest -q
uv run ruff check src tests scripts
uv run mypy src
uv run alembic upgrade head
uv run alembic check
```

Expected: all tests pass; Ruff and mypy report no errors; Alembic reports no new upgrade operations.

- [ ] **Step 2: Regenerate and diff the OpenAPI contract**

Run:

```bash
cd image-code
uv run python -c 'import json; from design_hub.interface.api.asgi import app; print(json.dumps(app.openapi(), ensure_ascii=False))' > ../image-web/openapi.json
cd ../image-web
npm run gen:api
git diff --exit-code -- openapi.json src/api/schema.d.ts
```

Expected: no diff, proving the checked-in generated contract matches the application.

- [ ] **Step 3: Run the full frontend gate**

Run:

```bash
cd image-web
npm ci --legacy-peer-deps
npm test
npm run lint
npm run typecheck
npm run build
```

Expected: all tests pass, lint/typecheck pass, and Vite emits the production bundle.

- [ ] **Step 4: Run a local authenticated smoke test**

Start disposable local dependencies and the app using the existing development settings. Verify:

```text
manager login
→ /admin overview
→ users page and status dialog
→ generation grid and detail
→ block one mock result
→ ordinary user sees “该图片暂不可用”
→ restore result
→ usage page shows mock-free live-record fixtures only
→ audit page contains role/status/moderation/model actions
```

Do not send real GPT Image or Doubao traffic for this smoke test.

- [ ] **Step 5: Write the QA issue**

The issue acceptance matrix must list:

```text
1. manager-only route and API authorization
2. self/last-manager lockout protection
3. disabled Bearer and SSE token rejection
4. generation/edit retry counting; poll/download exclusion
5. Doubao multi-round token capture
6. cross-user task/input/output preview
7. block/restore enforcement across history, Chat, download, reverse, edit, background
8. one-hour previously signed URL limitation
9. safe audit contents and transaction rollback
10. pagination/filter stability and historical-data labels
```

- [ ] **Step 6: Commit**

```bash
git add image-code/docs/superpowers/specs/2026-07-30-admin-console-design.md \
  image-issues/ISSUE-0070-管理后台验收.md
git commit -m "docs: hand admin console to QA" \
  -m "Record the completed implementation state and provide an independent acceptance matrix for permissions, metering, moderation, and audit behavior."
```

---

## Plan Self-Review

- Spec coverage: all design sections map to Tasks 1–11.
- Historical data: Tasks 1 and 5 preserve safe defaults and refuse inferred call/token data.
- GPT Image semantics: Task 3 counts each generation/edit POST and explicitly excludes poll/download.
- Doubao usage: Task 4 handles the final empty-choices usage chunk and multi-round calls.
- Moderation: Tasks 6 and 10 cover server enforcement and neutral user UI.
- Authorization: Task 2 covers current database status/role for Bearer and SSE.
- Audit atomicity: Tasks 2, 6, and 7 write mutation and audit in one transaction.
- Pagination and bounded queries: Task 5.
- Existing model configuration: Tasks 7–9.
- Deferred features remain absent.
- Placeholder scan: no unresolved markers or unnamed error-handling steps remain.
