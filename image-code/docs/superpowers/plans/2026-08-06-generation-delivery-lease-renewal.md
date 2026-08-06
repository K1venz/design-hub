# 生成任务消息租约续期实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 为所有图片模型的长耗时任务续期 Redis Stream delivery，避免正常任务被 `XAUTOCLAIM` 重复投递，同时保持现有用户并发、Provider 槽位和产品状态不变。

**Architecture:** 在通用 `TaskBroker` 边界增加单条 delivery 续期能力，由 Redis 实现通过 `XCLAIM JUSTID` 重置消息 idle。`GenerationWorker` 在现有数据库心跳中调用该能力；不增加租约服务、重试框架、模型分支或新任务状态。

**Tech Stack:** Python 3.12、asyncio、redis-py asyncio、SQLAlchemy、Pydantic Settings、pytest、uv。

## Global Constraints

- Python 命令只能通过 `uv run` 执行，不使用系统 Python。
- 不增加依赖，不修改依赖清单。
- 修复必须与 Nano Banana 2、万象 2.7 及未来模型解耦。
- 不改变用户并发上限、Worker `read_count`、Provider 槽位、计费和用户可见任务状态。
- 非 I/O 逻辑 fail-fast；不增加自动重试、fallback、兼容层或错误吞噬。
- 每个任务严格执行测试先失败、最小实现、测试通过、单独提交。

---

## 文件结构

- 修改 `src/design_hub/ports/task_broker.py`：定义通用 delivery 续期协议。
- 修改 `src/design_hub/infrastructure/queue/redis_streams.py`：实现 Redis Stream idle 续期并校验响应。
- 修改 `src/design_hub/application/tasking/worker.py`：在现有单任务心跳中协调数据库与 Redis delivery 续期。
- 修改 `src/design_hub/config/settings.py`：暴露 Worker 心跳周期并校验其小于消息回收窗口。
- 修改 `src/design_hub/interface/worker.py`：使用已验证的心跳配置组装 Worker。
- 修改 `tests/test_redis_streams.py`：覆盖 Redis 命令参数、成功、租约丢失和非法响应。
- 修改 `tests/test_generation_worker.py`：覆盖长耗时同步/异步模型、租约丢失和现有槽位续期。
- 修改 `tests/test_process_composition.py`：覆盖心跳与回收窗口的配置不变量。
- 修改 `tests/integration/test_stage_a_task_chain.py`：让 ACK 故障代理完整转发通用 Broker 续期能力。

### Task 1: 通用 Broker delivery 续期能力

**Files:**
- Modify: `src/design_hub/ports/task_broker.py:13-28`
- Modify: `src/design_hub/infrastructure/queue/redis_streams.py:20-35,100-124`
- Test: `tests/test_redis_streams.py:12-150`

**Interfaces:**
- Consumes: Redis `xclaim(name, groupname, consumername, min_idle_time, message_ids, idle=0, justid=True)`。
- Produces: `TaskBroker.renew(*, consumer: str, redis_id: str) -> bool`。

- [ ] **Step 1: 写 Broker 续期失败测试**

在 `_FakeRedis` 增加 `renew_result: object = []` 和 `xclaim()` 记录器，然后增加：

```python
def test_renew_resets_pending_delivery_idle_without_incrementing_retries() -> None:
    async def run() -> None:
        redis = _FakeRedis()
        redis.renew_result = ["10-0"]
        broker = RedisTaskBroker(redis)

        assert await broker.renew(consumer="worker-1", redis_id="10-0") is True
        assert redis.calls == [
            (
                "xclaim",
                (
                    "design-hub:generation:v1",
                    "generation-workers-v1",
                    "worker-1",
                    0,
                    ("10-0",),
                ),
                {"idle": 0, "justid": True},
            )
        ]

    asyncio.run(run())


def test_renew_reports_lost_delivery_and_rejects_malformed_response() -> None:
    async def run() -> None:
        redis = _FakeRedis()
        broker = RedisTaskBroker(redis)
        assert await broker.renew(consumer="worker-1", redis_id="10-0") is False

        redis.renew_result = [1]
        with pytest.raises(TypeError, match="XCLAIM response"):
            await broker.renew(consumer="worker-1", redis_id="10-0")

    asyncio.run(run())
```

- [ ] **Step 2: 运行测试并确认因接口缺失而失败**

Run: `uv run pytest tests/test_redis_streams.py::test_renew_resets_pending_delivery_idle_without_incrementing_retries tests/test_redis_streams.py::test_renew_reports_lost_delivery_and_rejects_malformed_response -q`

Expected: FAIL，`RedisTaskBroker` 没有 `renew`，或 fake Redis 没有 `xclaim`。

- [ ] **Step 3: 实现最小 Broker 协议与 Redis 映射**

在协议中加入：

```python
async def renew(self, *, consumer: str, redis_id: str) -> bool: ...
```

在 `RedisStreamClient` 中加入：

```python
async def xclaim(self, *args: object, **kwargs: object) -> object: ...
```

在 `RedisTaskBroker` 中实现：

```python
async def renew(self, *, consumer: str, redis_id: str) -> bool:
    response = await self._client.xclaim(
        _GENERATION_STREAM,
        _GENERATION_GROUP,
        consumer,
        0,
        (redis_id,),
        idle=0,
        justid=True,
    )
    if not isinstance(response, Sequence) or isinstance(response, (str, bytes)):
        raise TypeError("Redis XCLAIM response must be a sequence")
    if not all(isinstance(message_id, str) for message_id in response):
        raise TypeError("Redis XCLAIM response contains an invalid message id")
    return redis_id in response
```

- [ ] **Step 4: 运行 Broker 测试**

Run: `uv run pytest tests/test_redis_streams.py -q`

Expected: PASS，全部 Redis Stream 测试通过。

- [ ] **Step 5: 提交 Broker 单元**

```powershell
git add -- src/design_hub/ports/task_broker.py src/design_hub/infrastructure/queue/redis_streams.py tests/test_redis_streams.py
git commit -m "feat: renew active generation deliveries" -m "Add a reusable TaskBroker delivery renewal contract and map it to Redis XCLAIM JUSTID so long-running consumers keep their pending messages alive without inflating retry counts."
```

### Task 2: Worker 单任务心跳集成

**Files:**
- Modify: `src/design_hub/application/tasking/worker.py:216-418`
- Modify: `tests/test_generation_worker.py:106-284,479-496`
- Modify: `tests/integration/test_stage_a_task_chain.py:217-227`

**Interfaces:**
- Consumes: `TaskBroker.renew(*, consumer: str, redis_id: str) -> bool` from Task 1。
- Produces: `_heartbeat_loop(work: GenerationWorkItem, delivery: Delivery) -> None`，同时续期数据库和 Redis delivery。

- [ ] **Step 1: 扩展 Worker 测试替身并写三种失败测试**

让 `_Broker` 记录续期并允许模拟租约丢失：

```python
class _Broker:
    def __init__(self, repository: _Repository) -> None:
        self.repository = repository
        self.acks: list[str] = []
        self.renewals: list[tuple[str, str]] = []
        self.renewed = True

    async def renew(self, *, consumer: str, redis_id: str) -> bool:
        self.renewals.append((consumer, redis_id))
        return self.renewed
```

把现有长耗时测试的断言收紧为：

```python
assert "heartbeat" in repository.actions
assert broker.renewals
assert set(broker.renewals) == {("worker-1", "10-0")}
assert "refresh" in slots.actions
assert executor.submits == 1
assert broker.acks == ["10-0"]
```

增加 delivery 租约丢失测试：

```python
def test_lost_delivery_lease_cancels_provider_operation() -> None:
    async def run() -> None:
        repository = _Repository(_work())
        executor = _Executor(delay_seconds=0.03)
        worker, broker, slots = _worker(
            repository,
            executor,
            heartbeat_seconds=0.005,
        )
        broker.renewed = False

        with pytest.raises(DataInvariantError, match="delivery lease lost"):
            await worker.process(_delivery())

        assert executor.submits == 1
        assert broker.acks == []
        assert "complete" not in repository.actions
        assert slots.actions[-1] == "release"

    asyncio.run(run())
```

给 `_Executor.__init__()` 增加 `resume_delay_seconds: float = 0`，保存后在 `resume()` 返回前执行：

```python
if self.resume_delay_seconds:
    await asyncio.sleep(self.resume_delay_seconds)
```

增加异步 Provider 轮询测试：

```python
def test_long_provider_resume_refreshes_delivery_lease() -> None:
    async def run() -> None:
        repository = _Repository(_work())
        executor = _Executor(
            result=SubmittedTask("provider-task-1"),
            resume_delay_seconds=0.03,
        )
        worker, broker, _slots = _worker(
            repository,
            executor,
            heartbeat_seconds=0.005,
        )

        await worker.process(_delivery())

        assert executor.submits == 1
        assert executor.resumes == 1
        assert set(broker.renewals) == {("worker-1", "10-0")}
        assert broker.acks == ["10-0"]

    asyncio.run(run())
```

- [ ] **Step 2: 运行三种测试并确认都因续期能力尚未接入而失败**

Run: `uv run pytest tests/test_generation_worker.py::test_long_provider_submit_refreshes_database_and_slot_leases tests/test_generation_worker.py::test_lost_delivery_lease_cancels_provider_operation tests/test_generation_worker.py::test_long_provider_resume_refreshes_delivery_lease -q`

Expected: FAIL；长耗时测试的 `broker.renewals` 为空，租约丢失测试未抛出 `DataInvariantError`。

- [ ] **Step 3: 把 delivery 传入现有守护循环并调用 Broker 续期**

三个 `_guard_operation()` 调用都传入当前 `delivery`。守护循环修改为：

```python
async def _heartbeat_loop(
    self,
    work: GenerationWorkItem,
    delivery: Delivery,
) -> None:
    while True:
        await asyncio.sleep(self._heartbeat_seconds)
        await self._repository.heartbeat(
            work.spec.item_id,
            self._worker_id,
            self._lease_seconds,
        )
        renewed = await self._broker.renew(
            consumer=self._worker_id,
            redis_id=delivery.redis_id,
        )
        if not renewed:
            raise DataInvariantError(
                f"delivery lease lost for generation item {work.spec.item_id}"
            )
```

`_guard_operation()` 创建心跳任务时使用 `_heartbeat_loop(work, delivery)`。保留现有 FIRST_COMPLETED 和取消语义，不增加重试。

- [ ] **Step 4: 运行三种测试并确认通过**

Run: `uv run pytest tests/test_generation_worker.py::test_long_provider_submit_refreshes_database_and_slot_leases tests/test_generation_worker.py::test_lost_delivery_lease_cancels_provider_operation tests/test_generation_worker.py::test_long_provider_resume_refreshes_delivery_lease -q`

Expected: PASS。

- [ ] **Step 5: 运行完整 Worker 测试**

Run: `uv run pytest tests/test_generation_worker.py -q`

Expected: PASS，Worker 单元测试全部通过。

- [ ] **Step 6: 更新 ACK 故障代理的通用协议转发**

在 `_FailFirstAck` 中增加：

```python
async def renew(self, *, consumer: str, redis_id: str) -> bool:
    return await self.broker.renew(consumer=consumer, redis_id=redis_id)
```

Run: `uv run pytest tests/integration/test_stage_a_task_chain.py -q`

Expected: 在配置了集成环境时 PASS；未配置时按现有条件 SKIP，不出现收集或类型错误。

- [ ] **Step 7: 提交 Worker 集成单元**

```powershell
git add -- src/design_hub/application/tasking/worker.py tests/test_generation_worker.py tests/integration/test_stage_a_task_chain.py
git commit -m "fix: keep long-running image tasks owned" -m "Renew each Redis delivery alongside the existing database heartbeat and fail fast when ownership is lost. Cover synchronous and asynchronous providers without adding model-specific behavior or retries."
```

### Task 3: 配置不变量与并发回归

**Files:**
- Modify: `src/design_hub/config/settings.py:3-31`
- Modify: `src/design_hub/interface/worker.py:128-154`
- Modify: `tests/test_process_composition.py:156-202`

**Interfaces:**
- Consumes: `Settings.worker_reclaim_idle_ms: int`。
- Produces: `Settings.worker_heartbeat_seconds: float`，并保证 `worker_heartbeat_seconds * 1000 < worker_reclaim_idle_ms`。

- [ ] **Step 1: 写配置不变量失败测试**

在 `tests/test_process_composition.py` 导入 `ValidationError` 和 `Settings`，直接在 `pytest.raises` 内构造非法配置：

```python
def test_worker_heartbeat_must_precede_delivery_reclaim() -> None:
    with pytest.raises(ValidationError, match="worker heartbeat must be shorter"):
        Settings(
            _env_file=None,
            worker_heartbeat_seconds=15,
            worker_reclaim_idle_ms=15_000,
        )
```

- [ ] **Step 2: 运行配置测试并确认缺少校验**

Run: `uv run pytest tests/test_process_composition.py::test_worker_heartbeat_must_precede_delivery_reclaim -q`

Expected: FAIL，因为当前设置接受相等的心跳和回收窗口。

- [ ] **Step 3: 增加最小配置字段和跨字段校验**

在 `settings.py` 导入 `model_validator`，增加字段与校验：

```python
worker_heartbeat_seconds: float = Field(default=15.0, gt=0)

@model_validator(mode="after")
def validate_worker_lease_timing(self) -> "Settings":
    if self.worker_heartbeat_seconds * 1000 >= self.worker_reclaim_idle_ms:
        raise ValueError("worker heartbeat must be shorter than delivery reclaim idle")
    return self
```

在 `interface/worker.py` 中把硬编码 `heartbeat_seconds=15` 改成：

```python
heartbeat_seconds=settings.worker_heartbeat_seconds,
```

- [ ] **Step 4: 运行配置与组装测试**

Run: `uv run pytest tests/test_process_composition.py tests/test_docs_gate.py tests/test_task_observability.py -q`

Expected: PASS，默认配置保持兼容，非法租约时序 fail-fast。

- [ ] **Step 5: 运行并发行为回归**

Run: `uv run pytest tests/test_generation_worker.py::test_long_provider_submit_refreshes_database_and_slot_leases tests/test_process_composition.py::test_worker_runtime_bounds_claimed_deliveries_and_drains_on_stop tests/test_redis_slots.py -q`

Expected: PASS；长任务续期、两个 Worker 活动槽位及按模型/清晰度 Provider 限流均保持现有行为。

- [ ] **Step 6: 提交配置与并发单元**

```powershell
git add -- src/design_hub/config/settings.py src/design_hub/interface/worker.py tests/test_process_composition.py
git commit -m "fix: validate generation lease timing" -m "Make the worker heartbeat interval explicit and reject configurations that allow Redis delivery reclaim before a live worker can renew ownership. Preserve existing concurrency limits and defaults."
```

### Task 4: 全量验证与收口

**Files:**
- Verify only; no planned production changes.

**Interfaces:**
- Consumes: Tasks 1-3 的最终代码。
- Produces: 可复核的测试、静态检查和 Git 状态证据。

- [ ] **Step 1: 运行 Python 全量测试**

Run: `uv run pytest -q`

Expected: PASS，无失败；需要外部 MySQL/Redis 的测试仅按项目既有条件 SKIP。

- [ ] **Step 2: 运行 lint 和类型检查**

Run: `uv run ruff check .`

Expected: PASS，无 lint 错误。

Run: `uv run mypy src`

Expected: PASS，无类型错误。

- [ ] **Step 3: 检查变更边界**

Run: `git diff HEAD~3 --check`

Expected: PASS，无空白错误。

Run: `git status --short`

Expected: 空输出，所有实现单元均已提交，未触碰模型、计费或前端状态代码。

- [ ] **Step 4: 汇总验收证据**

确认以下事实均由测试输出支持：长耗时同步和异步 Provider 都续期 delivery；租约丢失会停止操作且不 ACK；正常并发未串行化；Provider 槽位规则未改变；配置无法让心跳周期大于或等于回收窗口。
