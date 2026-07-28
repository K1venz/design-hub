# Design Hub image generation service

Stage A separates request handling from image execution:

```text
API -> MySQL transaction (job + items + ledger + outbox)
    -> Dispatcher -> Redis Stream -> Worker -> Provider
    -> MySQL terminal state -> event outbox -> Redis event stream -> SSE
```

MySQL is the source of truth. Redis only carries minimal routing envelopes and
replayable progress events; prompts, image bytes, credentials, and signed URLs
must not enter Redis.

## Local processes

Start a local Redis separately, apply the database migration, and run the API
and Worker as two processes:

```bash
uv run alembic upgrade head
uv run uvicorn design_hub.interface.api.asgi:app --host 0.0.0.0 --port 8000
uv run python -m design_hub.interface.worker
```

Development defaults are in `.env.development`. Real credentials belong in the
ignored `.env` file or the process environment.

The fixed Redis names are:

- Task stream: `design-hub:generation:v1`
- Consumer group: `generation-workers-v1`
- Per-job events: `design-hub:events:{job_id}` with a 24-hour TTL

On `SIGTERM`, the Worker stops claiming new deliveries, allows active work up to
30 seconds, then cancels remaining coroutines. Provider slots use renewable
Redis leases, so a killed Worker cannot hold capacity forever.

## Stage A migration and rollback

Migration `a7b8c9d0e1f2` adds `generation_item` and `outbox_event`, adds the
listing idempotency snapshot, and gives historical ledger rows deterministic
`legacy:{id}` operation keys.

Before upgrading production:

1. Back up MySQL and record `uv run alembic current`.
2. Stop API and Worker writes.
3. Run `uv run alembic upgrade a7b8c9d0e1f2`.
4. Start one Worker at the default 3 standard / 1 4K Provider slots.
5. Verify health, Outbox age, Pending count, terminal aggregation, and SSE.

Application rollback should first stop API submissions and Workers. Drain or
preserve Pending messages, restore the pre-migration application and database
backup, and only then remove Stage A Redis keys. Do not run the Alembic
downgrade against live accepted jobs: the downgrade removes task and Outbox
records.

## Crash-recovery integration tests

The opt-in suite uses real services and deliberately flushes the selected Redis
database. Use a dedicated, disposable Redis database and a dedicated MySQL
schema already migrated to `a7b8c9d0e1f2`:

```bash
export STAGE_A_TEST_DB_URL='mysql+aiomysql://user:password@127.0.0.1/image_gen_stage_a_test'
export STAGE_A_TEST_REDIS_URL='redis://127.0.0.1:6379/15'
uv run pytest -q tests/integration/test_stage_a_task_chain.py
```

Without both variables, the suite skips with an explicit reason. It exercises
transactional submission, Outbox dispatch, Pending recovery after consumer and
client loss, idempotent API restart, duplicate delivery, cancellation and
single terminal aggregation, async Provider resume, DB commit before failed
ACK, and SSE replay. Synchronous submission ambiguity and storage-commit
failure are covered by deterministic unit tests because they require precise
fault injection rather than a live Provider call.

Run the normal gates with:

```bash
uv run pytest -q
uv run mypy src
uv run ruff check src tests scripts
uv run alembic check
```
