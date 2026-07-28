# Stage A Redis Task Foundation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 将现有 listing 出图迁移为 MySQL 事实源、事务 Outbox、Redis Streams 和独立 Worker 驱动的单图任务链，在不增加质检耗时的前提下，为 200 人上线目标提供可恢复、可限流、可观测的任务底座。

**Architecture:** API 只校验和原子写入 Job、GenerationItem、成本预扣与 Outbox；Dispatcher 发布最少字段的 Redis 消息；Worker 以数据库状态机和租约守门，按 Provider/档位获取 Redis 全局槽位，执行单张图片并在数据库提交终态后 ACK。Redis Stream 同时承载可回放的 Job 事件；MySQL 始终是任务和计费事实源。

**Tech Stack:** Python 3.12、FastAPI、SQLAlchemy Async、Alembic、MySQL、`redis.asyncio`、Redis Streams、structlog、Prometheus、Sentry、pytest。

## Global Constraints

- 执行数据库 Task 前，必须再次取得用户对“新增两表、调整两表、回填旧账本操作键”的明确许可。
- Python 命令只用 `uv run`；依赖只用 `uv add redis`，不得手改依赖清单或使用系统 Python。
- Redis 使用托管实例，不与当前 2C/3.8GB API 服务器同机。
- 不引入 Kafka、RabbitMQ、Kubernetes、OpenTelemetry、通用 Broker 抽象、多区域或自动扩缩容。
- 非 I/O 逻辑 fail-fast；只有 Redis、Provider、TOS、数据库网络 I/O 允许受预算约束的有限重试。
- Redis 消息不得包含完整 Prompt、图片字节、API 密钥或预签名 URL。
- 生产代码不保留 `InProcessTaskQueue`、`InMemoryEventBus`、`ThrottledCommand` 的兼容层；测试可使用针对新端口的轻量 fake。
- 三条现有提交接口继续承载三种严格请求 schema，统一返回 `202`；不增加功能重复的通用提交接口。
- Provider 并发默认保持当前安全档位：普通 1K 全局 3、4K 全局 1。只有确认上游额度并通过压测后，运维才逐步提高到容量目标所需的 47–60。
- 每个 Task 按 TDD 执行：先写失败测试并实际观察失败，再做最小实现，跑定向测试和静态检查，最后单独提交。

---

## File Map

### New production files

- `src/design_hub/domain/tasking.py`：消息信封、任务状态、不可变执行快照。
- `src/design_hub/ports/generation_work.py`：提交、Outbox、任务状态与租约端口。
- `src/design_hub/ports/task_broker.py`：Redis Stream 消息收发端口。
- `src/design_hub/ports/provider_execution.py`：即时 Provider 与可恢复异步 Provider 的执行能力。
- `src/design_hub/infrastructure/db/generation_work_repo.py`：原子提交、状态转换、Outbox 和 Job 聚合。
- `src/design_hub/infrastructure/queue/redis_streams.py`：任务 Stream、事件 Stream、Consumer Group。
- `src/design_hub/infrastructure/queue/redis_slots.py`：带租约的全局 Provider 并发槽位。
- `src/design_hub/application/tasking/outbox_dispatcher.py`：Outbox 发布循环。
- `src/design_hub/application/tasking/worker.py`：领取、租约、执行、终态、ACK。
- `src/design_hub/application/tasking/health.py`：Redis 最近健康状态与背压估算。
- `src/design_hub/infrastructure/monitoring/logging.py`：structlog 配置与上下文。
- `src/design_hub/infrastructure/monitoring/task_metrics.py`：业务指标。
- `src/design_hub/interface/worker.py`：Worker 进程入口。
- `migrations/versions/a7b8c9d0e1f2_stage_a_reliable_generation.py`：Stage A 数据迁移。

### Main files to modify

- `src/design_hub/infrastructure/db/models.py`
- `src/design_hub/infrastructure/ledger/sqlalchemy_ledger.py`
- `src/design_hub/application/cost/guard.py`
- `src/design_hub/application/listing/listing_service.py`
- `src/design_hub/application/listing/job_launcher.py`
- `src/design_hub/ports/model_provider.py`
- `src/design_hub/infrastructure/providers/apinebula_async.py`
- `src/design_hub/interface/api/routes/listing.py`
- `src/design_hub/interface/api/asgi.py`
- `src/design_hub/interface/api/app.py`
- `src/design_hub/config/settings.py`
- `src/design_hub/infrastructure/monitoring/setup.py`
- `.env.development`
- `README.md`

### Production files to delete after replacement tests pass

- `src/design_hub/ports/task_queue.py`
- `src/design_hub/infrastructure/queue/in_process.py`
- `src/design_hub/infrastructure/events/memory.py`
- `src/design_hub/application/rate_limit.py`
- `src/design_hub/application/listing/commands.py`

---

## Task 1: Define the state machine and immutable item snapshot

**Files:** Create `src/design_hub/domain/tasking.py`; test `tests/test_tasking_domain.py`.

- [ ] Write tests for message JSON round-trip, required envelope fields, legal transitions, terminal detection, and exclusion of secrets/full Prompt from Redis fields.
- [ ] Run `uv run pytest -q tests/test_tasking_domain.py` and observe the missing types failure.
- [ ] Implement `GenerationItemStatus`, `OperationType`, `RenderTier`, `ReferenceSnapshot`, `GenerationItemSpec`, and `TaskMessage`.

```python
class GenerationItemStatus(StrEnum):
    WAITING = "waiting"
    QUEUED = "queued"
    CLAIMED = "claimed"
    SUBMITTING = "submitting"
    SUBMITTED = "submitted"
    PROCESSING = "processing"
    STORING = "storing"
    GENERATED = "generated"
    CANCELLED = "cancelled"
    TIMED_OUT = "timed_out"
    FAILED = "failed"
    SUBMISSION_UNCERTAIN = "submission_uncertain"


@dataclass(frozen=True)
class GenerationItemSpec:
    item_id: str
    sequence: int
    image_type: str | None
    operation_type: OperationType
    render_tier: RenderTier
    final_prompt: str
    model: ModelName
    ratio: str
    size: tuple[int, int]
    quality: str | None
    seed: int
    references: tuple[ReferenceSnapshot, ...]
    reserved_cost: Decimal
```

- [ ] Keep an explicit transition table. `require_transition` raises `InvalidTaskTransition`; it never coerces or silently skips.
- [ ] Run `uv run pytest -q tests/test_tasking_domain.py && uv run mypy src/design_hub/domain/tasking.py && uv run ruff check src/design_hub/domain/tasking.py tests/test_tasking_domain.py`.
- [ ] Commit `feat: define generation task state model`.

## Task 2: Add Stage A schema and idempotent ledger keys

**Approval gate:** Stop and obtain explicit database migration permission before this Task.

**Files:** Modify `infrastructure/db/models.py`, `infrastructure/ledger/sqlalchemy_ledger.py`, `ports/ledger.py`; create migration `a7b8c9d0e1f2`; test `tests/test_generation_work_repo.py`.

- [ ] Write DB tests for every item snapshot field, unique `(job_id, sequence)`, item `operation_id`, `(user_id, idempotency_key)`, and ledger `operation_id`.
- [ ] Test that an identical duplicate ledger operation is idempotent, while changed user/amount raises a data invariant error.
- [ ] Run the tests and observe schema failures.
- [ ] Add `GenerationItemRow` and `OutboxEventRow`; index `(status, lease_expires_at)`, `(published_at, created_at)`, and `job_id`.
- [ ] Add `ListingJobRow.idempotency_key` and `CostLedgerEntry.operation_id`.
- [ ] Set migration `down_revision = "f3a4b5c6d7e8"` and backfill historical ledger rows as `legacy:{id}` before applying non-null/unique constraints. Do not add runtime legacy branches.
- [ ] Change ledger writes to require `operation_id`. Handle only the expected unique-key collision; compare the existing row exactly and let unrelated `IntegrityError` propagate.
- [ ] Run:

```bash
uv run alembic upgrade head
uv run pytest -q tests/test_generation_work_repo.py tests/test_listing_history_persistence.py
uv run alembic downgrade f3a4b5c6d7e8
uv run alembic upgrade head
uv run mypy src
uv run ruff check src tests
```

- [ ] Commit `feat: persist reliable generation tasks`.

## Task 3: Implement one transactional submission repository

**Files:** Create `ports/generation_work.py`, `infrastructure/db/generation_work_repo.py`; modify `application/cost/guard.py`; extend `tests/test_generation_work_repo.py`.

- [ ] Write failing tests proving one transaction creates the Job, all Items, one reserve ledger row per Item, and only the first Item’s Outbox event; injected failure must leave no partial rows.
- [ ] Test idempotency replay returns the original `job_id`; same key with a different canonical request fingerprint raises `IdempotencyConflict`.
- [ ] Define:

```python
@dataclass(frozen=True)
class JobSubmission:
    job: ListingJobStart
    idempotency_key: str
    request_fingerprint: str
    items: tuple[GenerationItemSpec, ...]
    trace_id: str
    request_id: str


class GenerationWorkRepository(Protocol):
    async def submit(self, submission: JobSubmission) -> SubmitResult: ...
    async def fetch_outbox_batch(self, *, limit: int) -> tuple[OutboxRecord, ...]: ...
    async def mark_outbox_published(self, event_id: str, redis_id: str) -> None: ...
    async def record_outbox_failure(self, event_id: str, error: str) -> None: ...
```

- [ ] Validate `BudgetPolicy` before the transaction, but insert all reserves inside that transaction with keys `reserve:{item_id}`. Do not add a budget counter table in Stage A.
- [ ] Compute `request_fingerprint` from SHA-256 of canonical JSON after validation and model selection.
- [ ] Lock the user row with `SELECT ... FOR UPDATE` while checking “one active Job per user” and submitting.
- [ ] Run `uv run pytest -q tests/test_generation_work_repo.py && uv run mypy src && uv run ruff check src tests/test_generation_work_repo.py`.
- [ ] Commit `feat: add atomic generation submission`.

## Task 4: Refactor listing requests into immutable task plans

**Files:** Modify `application/listing/listing_service.py`, `application/listing/job_launcher.py`, `application/listing/requests.py`; create `tests/test_listing_submission.py`; update `tests/test_listing_validation.py`.

- [ ] Write failing generate/clone/edit planning tests for exact Prompt, seed, quality, size, reference key order/role, item count, and reserved cost.
- [ ] Add pure `ListingTaskPlanner` returning `JobSubmission`; it must not load image bytes or create signed URLs.
- [ ] Snapshot roles in order: generate product uploads; clone product then reference uploads; edit generated source then root product anchors.
- [ ] Replace batch `generate/clone/edit` orchestration with `execute_item(spec, references) -> GeneratedImage`; each call requests exactly one image.
- [ ] Replace launcher dependencies on the old Queue, History, Events, and in-memory limiter with Planner, `GenerationWorkRepository`, and `RedisHealthState`.
- [ ] Require `Idempotency-Key` at the HTTP boundary and reject missing/blank values before any write.
- [ ] Run `uv run pytest -q tests/test_listing_submission.py tests/test_listing_validation.py && uv run mypy src && uv run ruff check src tests`.
- [ ] Commit `refactor: persist listing execution snapshots`.

## Task 5: Add Redis Streams for tasks and replayable Job events

**Files:** Create `ports/task_broker.py`, `infrastructure/queue/redis_streams.py`, `tests/test_redis_streams.py`, `tests/test_redis_events.py`; update dependencies via CLI.

- [ ] Run `uv add redis`.
- [ ] Write failing tests using an injected async Redis fake for group creation with `MKSTREAM`, `XADD`, `XREADGROUP`, `XACK`, `XAUTOCLAIM`, malformed messages, event TTL/MAXLEN, and `Last-Event-ID` replay.
- [ ] Define the narrow broker contract:

```python
class TaskBroker(Protocol):
    async def ensure_group(self) -> None: ...
    async def publish(self, message: TaskMessage) -> str: ...
    async def read(self, *, consumer: str, count: int, block_ms: int) -> tuple[Delivery, ...]: ...
    async def autoclaim(
        self, *, consumer: str, min_idle_ms: int, count: int
    ) -> tuple[Delivery, ...]: ...
    async def ack(self, redis_id: str) -> None: ...
```

- [ ] Use `redis.asyncio.Redis.from_url`, socket timeouts, and `await redis.aclose()`. Use stream `design-hub:generation:v1`, group `generation-workers-v1`.
- [ ] Use `design-hub:events:{job_id}` with approximate MAXLEN 100 and 24-hour TTL. SSE uses `XREAD`, not a Consumer Group.
- [ ] Run `uv run pytest -q tests/test_redis_streams.py tests/test_redis_events.py && uv run mypy src && uv run ruff check src tests`.
- [ ] Commit `feat: add Redis Streams task broker`.

## Task 6: Dispatch Outbox and enforce admission/backpressure

**Files:** Create `application/tasking/outbox_dispatcher.py`, `application/tasking/health.py`, `tests/test_outbox_dispatcher.py`; modify `config/settings.py`.

- [ ] Test publish-before-mark ordering, duplicate publication after a crash, bounded Redis error storage, stale health rejection, and queue wait estimation.
- [ ] Implement batches of 100 and 500 ms idle polling. Retry Redis I/O with exponential backoff capped at 5 seconds; let database logic errors propagate.
- [ ] Add validated settings:

```python
redis_url: str
redis_health_interval_seconds: float = 2.0
redis_health_stale_seconds: float = 6.0
outbox_batch_size: int = 100
queue_soft_wait_seconds: int = 300
queue_confirm_wait_seconds: int = 900
queue_hard_depth: int = 2000
```

- [ ] Admission returns `normal`, `high_peak`, `confirmation_required`, or reject. Stage A rejects `confirmation_required` until the UI can explicitly confirm; it never silently enqueues >15 minute waits.
- [ ] Run `uv run pytest -q tests/test_outbox_dispatcher.py && uv run mypy src && uv run ruff check src tests/test_outbox_dispatcher.py`.
- [ ] Commit `feat: dispatch transactional outbox events`.

## Task 7: Make Provider submission recoverable

**Files:** Create `ports/provider_execution.py`, `tests/test_provider_execution.py`; modify `ports/model_provider.py`, `infrastructure/providers/apinebula_async.py`, `infrastructure/providers/openai_compat.py`, `tests/test_provider_contract.py`.

- [ ] Test async submit returns a persistable `provider_task_id`, resume never resubmits, sync Provider returns an immediate image, ambiguous sync timeout becomes `submission_uncertain`, and idempotency keys are only passed to supporting adapters.
- [ ] Split the async adapter into `submit_task`, `poll_task`, and `collect_task`, retaining bounded network retries and wall-clock budget.
- [ ] Implement:

```python
@dataclass(frozen=True)
class SubmittedTask:
    provider_task_id: str


@dataclass(frozen=True)
class ImmediateResult:
    image: GeneratedImage


class ProviderExecutor(Protocol):
    async def submit(
        self, request: ProviderRequest, *, operation_id: str
    ) -> SubmittedTask | ImmediateResult: ...
    async def resume(self, provider_task_id: str, request: ProviderRequest) -> GeneratedImage: ...
```

- [ ] Sync `resume` raises `UnsupportedProviderResume`; do not emulate recovery or retry an ambiguous non-idempotent submit.
- [ ] Run `uv run pytest -q tests/test_provider_execution.py tests/test_provider_contract.py && uv run mypy src && uv run ruff check src tests`.
- [ ] Commit `refactor: expose provider task lifecycle`.

## Task 8: Enforce distributed Provider concurrency

**Files:** Create `infrastructure/queue/redis_slots.py`, `tests/test_redis_slots.py`; modify `config/settings.py`.

- [ ] Test the global limit across two workers, lease renewal, owner-only release, expiry cleanup, and 1K/4K isolation.
- [ ] Implement a Lua-backed sorted-set semaphore per Provider/model/tier. Acquisition atomically removes expired members, checks cardinality, and inserts `{worker_id}:{item_id}` with lease-expiry score.
- [ ] Add defaults: standard concurrency 3, 4K concurrency 1, lease 30 seconds, refresh 10 seconds.
- [ ] Slot refresh failure stops new Provider calls. A previously submitted resumable task may poll without holding a submission slot.
- [ ] Run `uv run pytest -q tests/test_redis_slots.py && uv run mypy src && uv run ruff check src tests/test_redis_slots.py`.
- [ ] Commit `feat: enforce global provider concurrency`.

## Task 9: Build the per-image Worker state machine

**Files:** Create `application/tasking/worker.py`, `tests/test_generation_worker.py`; extend the generation repository and ledger implementation.

- [ ] Write scenario tests for happy path, duplicate delivery, stale claim takeover, ambiguous submission, persisted Provider task resume, refund/reconcile idempotency, next-item release, two-item user limit, cancellation, and Job terminal aggregation.
- [ ] Every repository transition must be compare-and-set with expected status; affected row count other than one raises `ConcurrentTaskMutation`.
- [ ] Implement this order:

```text
read/autoclaim
→ load item
→ terminal? ACK
→ claim with lease
→ materialize references from object keys
→ acquire provider slot
→ mark submitting
→ submit or resume
→ persist provider_task_id immediately
→ release next eligible item in the same transaction
→ poll/collect
→ persist image + item terminal + cost reconciliation + Job aggregate
→ publish event
→ ACK
```

- [ ] Heartbeat the DB lease every 15 seconds. If ownership is lost, stop local processing and do not ACK.
- [ ] Use `refund:{item_id}` and `reconcile:{item_id}` ledger keys. Store bounded user-safe errors; raw errors go only to redacted logs/Sentry.
- [ ] Run `uv run pytest -q tests/test_generation_worker.py && uv run mypy src && uv run ruff check src tests/test_generation_worker.py`.
- [ ] Commit `feat: execute recoverable image tasks`.

## Task 10: Wire HTTP admission and shared SSE

**Files:** Modify `ports/events.py`, `interface/api/routes/listing.py`, `interface/api/app.py`, `interface/listing_history_schemas.py`; update submission, Redis event, and chat SSE tests.

- [ ] Test `202`, required idempotency key, replay, `409` conflict, `503` unhealthy/hard cap, queue metadata, SSE `id:`/replay, and owner check before stream open.
- [ ] Return `job_id`, `queue_state`, and `estimated_wait_seconds`.
- [ ] Publish task-started, per-image generated/failed, and one terminal Job event only after matching DB commits.
- [ ] Query Job ownership before SSE subscription; authentication alone is insufficient.
- [ ] Run `uv run pytest -q tests/test_listing_submission.py tests/test_redis_events.py tests/test_chat_sse.py && uv run mypy src && uv run ruff check src tests`.
- [ ] Commit `feat: expose reliable listing task events`.

## Task 11: Add structured logs, metrics, and Sentry context

**Files:** Create `infrastructure/monitoring/logging.py`, `infrastructure/monitoring/task_metrics.py`, `tests/test_task_observability.py`; modify monitoring setup, API middleware, Dispatcher, and Worker.

- [ ] Test one request keeps the same `request_id`, `trace_id`, `job_id`, `item_id`, and `operation_id` across submission, Outbox, Worker, and Provider logs.
- [ ] Add middleware that accepts a valid `X-Request-ID` or creates one, binds/clears structlog contextvars, and returns `X-Request-ID`.
- [ ] Route stdlib logging through structlog; do not create a second business logger.
- [ ] Add an allowlist/redactor and tests proving no authorization header, API key, full Prompt, bytes, signed URL query, or Redis credentials are emitted.
- [ ] Add metrics for Outbox age/count, stream Pending/depth, item states/duration, Provider in-flight, uncertain submission, failures, and SSE connections.
- [ ] Tag Sentry with request/job/item/provider/error code, never Prompt or URL.
- [ ] Run `uv run pytest -q tests/test_task_observability.py && uv run mypy src && uv run ruff check src tests`.
- [ ] Commit `feat: instrument generation task lifecycle`.

## Task 12: Compose API/Worker processes and delete in-memory runtime

**Files:** Create `interface/worker.py`; modify `interface/api/asgi.py`, settings, `.env.development`, composition tests; delete the five legacy production files listed above.

- [ ] Test the API process cannot execute Provider calls; Worker owns Dispatcher, consumer, recovery, slots, and event publishing.
- [ ] Support:

```bash
uv run uvicorn design_hub.interface.api.asgi:app --host 0.0.0.0 --port 8000
uv run python -m design_hub.interface.worker
```

- [ ] API lifespan runs Redis health monitoring only. Worker ensures the group, runs Dispatcher/consumer/recovery, stops new claims on SIGTERM, waits at most 30 seconds, and releases owned slots.
- [ ] Delete old queue/event/rate-limit/command files and update all imports. Do not retain aliases or adapters.
- [ ] Run `uv run pytest -q && uv run mypy src && uv run ruff check src tests`.
- [ ] Commit `refactor: replace in-process generation runtime`.

## Task 13: Prove crash recovery end to end

**Files:** Create `tests/integration/test_stage_a_task_chain.py`; modify `README.md`.

- [ ] Add opt-in real MySQL/Redis tests, skipped with a clear reason when test URLs are absent.
- [ ] Cover API commit/dispatch, worker death after claim, duplicate Outbox publish, Redis restart with Pending, DB failure before ACK, API restart, worker resume by Provider task ID, sync ambiguity, cancellation, aggregation, and SSE replay.
- [ ] Document test environment variables, stream names, migration, API/Worker commands, and rollback.
- [ ] Run the integration test with `STAGE_A_TEST_DB_URL` and `STAGE_A_TEST_REDIS_URL`, then run the full unit/static suite.
- [ ] Commit `test: verify Stage A crash recovery`.

## Task 14: Add capacity harness and role handoffs

**Files:** Create `scripts/load_test_stage_a.py`; modify `README.md`; create `../image-issues/ISSUE-0066-stage-a-production-deployment.md` and `../image-issues/ISSUE-0067-stage-a-capacity-validation.md`.

- [ ] Build a bounded asyncio/httpx harness for 200 authenticated read/SSE sessions and 40 users × 5 Mock images. Report API P50/P95, queue wait P50/P95, completion, duplicates, and metrics.
- [ ] Require `--allow-real-provider` for real calls and print maximum estimated cost before sending.
- [ ] Assign ISSUE-0066 to 运维: managed Redis, separate API/Worker/MySQL, JSON logs, Prometheus, Sentry, secrets, backup/rollback, and staged concurrency.
- [ ] Assign ISSUE-0067 to QA: 200 reads/SSE; 200 Mock items; API P95 <500 ms excluding uploads; zero duplicate images; no permanent non-terminal items after crash; healthy Outbox age <10 seconds; real concurrency raised 3→10→20→40→approved ceiling only after each stable stage.
- [ ] Run `uv run python scripts/load_test_stage_a.py --help && uv run ruff check scripts/load_test_stage_a.py`.
- [ ] Commit `test: add Stage A capacity harness`.

## Task 15: Final verification and release gate

- [ ] Run:

```bash
uv run pytest -q
uv run mypy src
uv run ruff check src tests scripts
uv run alembic current
uv run alembic check
rg -n "InProcessTaskQueue|InMemoryEventBus|ThrottledCommand|UserRateLimiter" src tests
```

- [ ] The final `rg` has no production references. Review any test matches and remove tests that only preserve deleted architecture.
- [ ] Confirm every retry is I/O-bound, every ACK follows DB commit, and every accepted task has a terminal path.
- [ ] Confirm Ops/QA issues are closed; Stage A is not production-ready before both gates pass.
- [ ] Use `superpowers:requesting-code-review`, address findings, rerun the suite, then use `superpowers:verification-before-completion`.

## Capacity Notes

- Current 2C/3.8GB machine is not the Stage A production topology. It can remain QA, but API, Worker, MySQL, and managed Redis must be separated before the 200-user launch test.
- Queueing creates stability and recovery, not Provider capacity. At 70 seconds/image and a 5-minute target, about 47 slots are required; 56–60 is the margin target, bounded by the measured upstream quota.
- Stage A contains no fingerprint, AI quality inspection, repair, text layer, or export implementation. Those start only after this foundation passes recovery and capacity gates.
