import asyncio
import inspect
from datetime import UTC, datetime
from decimal import Decimal

import pytest
from redis.exceptions import ConnectionError

from design_hub.application.tasking.health import (
    RedisHealthState,
    RedisUnavailable,
)
from design_hub.application.tasking.runtime import GenerationWorkerRuntime
from design_hub.domain.enums import ModelName
from design_hub.domain.tasking import (
    GenerationItemSpec,
    GenerationItemStatus,
    OperationType,
    ReferenceSnapshot,
    ReferenceSource,
    RenderTier,
    TaskMessage,
)
from design_hub.infrastructure.queue.redis_health import (
    RedisHealthMonitor,
    RedisQueueSnapshotReader,
)
from design_hub.infrastructure.storage.reference_materializer import (
    StoredReferenceMaterializer,
)
from design_hub.interface import worker as worker_entrypoint
from design_hub.interface.api import asgi
from design_hub.ports.generation_work import GenerationWorkItem
from design_hub.ports.task_broker import Delivery


def _delivery(sequence: int) -> Delivery:
    item_id = f"item-{sequence}"
    return Delivery(
        redis_id=f"{sequence}-0",
        message=TaskMessage(
            schema_version=1,
            message_id=f"message-{sequence}",
            trace_id="trace-1",
            request_id="request-1",
            job_id="job-1",
            item_id=item_id,
            operation_id=f"operation-{sequence}",
            operation_type=OperationType.GENERATE_IMAGE,
            user_id="user-1",
            created_at=datetime(2026, 7, 28, tzinfo=UTC),
        ),
    )


class _Dispatcher:
    def __init__(self) -> None:
        self.calls = 0

    async def dispatch_once(self) -> int:
        self.calls += 1
        return 0


class _RuntimeBroker:
    def __init__(self, deliveries: list[Delivery]) -> None:
        self.deliveries = deliveries
        self.ensured = False
        self.read_counts: list[int] = []

    async def ensure_group(self) -> None:
        self.ensured = True

    async def autoclaim(
        self, *, consumer: str, min_idle_ms: int, count: int
    ) -> tuple[Delivery, ...]:
        return ()

    async def read(
        self, *, consumer: str, count: int, block_ms: int
    ) -> tuple[Delivery, ...]:
        self.read_counts.append(count)
        batch = tuple(self.deliveries[:count])
        del self.deliveries[:count]
        if not batch:
            await asyncio.sleep(0.01)
        return batch


class _BlockingWorker:
    def __init__(self, expected_started: int) -> None:
        self.expected_started = expected_started
        self.started_ids: list[str] = []
        self.started = asyncio.Event()
        self.release = asyncio.Event()

    async def process(self, delivery: Delivery) -> None:
        self.started_ids.append(delivery.redis_id)
        if len(self.started_ids) == self.expected_started:
            self.started.set()
        await self.release.wait()


def test_api_and_worker_have_separate_composition_roots() -> None:
    api_source = inspect.getsource(asgi)
    worker_source = inspect.getsource(worker_entrypoint)

    assert "ProviderExecutionAdapter" not in api_source
    assert "build_registry(" not in api_source
    assert "GenerationWorkerRuntime" not in api_source
    assert "ProviderExecutionAdapter" in worker_source
    assert "GenerationWorkerRuntime" in worker_source


def test_worker_runtime_bounds_claimed_deliveries_and_drains_on_stop() -> None:
    async def run() -> None:
        broker = _RuntimeBroker([_delivery(index) for index in range(1, 5)])
        worker = _BlockingWorker(expected_started=2)
        stop = asyncio.Event()
        runtime = GenerationWorkerRuntime(
            dispatcher=_Dispatcher(),  # type: ignore[arg-type]
            broker=broker,  # type: ignore[arg-type]
            worker=worker,  # type: ignore[arg-type]
            consumer_name="worker-1",
            read_count=2,
            read_block_ms=10,
            dispatcher_interval_seconds=0.01,
            shutdown_timeout_seconds=1,
        )

        running = asyncio.create_task(runtime.run(stop))
        await asyncio.wait_for(worker.started.wait(), timeout=1)
        await asyncio.sleep(0)
        assert broker.ensured is True
        assert worker.started_ids == ["1-0", "2-0"]
        assert all(count <= 2 for count in broker.read_counts)

        stop.set()
        worker.release.set()
        await asyncio.wait_for(running, timeout=1)
        assert worker.started_ids == ["1-0", "2-0"]

    asyncio.run(run())


class _RedisHealthClient:
    def __init__(
        self,
        *,
        groups: list[dict[str, object]] | None = None,
        error: Exception | None = None,
    ) -> None:
        self.groups = groups or []
        self.error = error

    async def ping(self) -> object:
        if self.error is not None:
            raise self.error
        return True

    async def xinfo_groups(self, name: str) -> list[dict[str, object]]:
        if self.error is not None:
            raise self.error
        return self.groups


def test_queue_snapshot_counts_pending_and_lag() -> None:
    async def run() -> None:
        reader = RedisQueueSnapshotReader(
            client=_RedisHealthClient(
                groups=[
                    {
                        "name": "generation-workers-v1",
                        "pending": 3,
                        "lag": 7,
                    }
                ]
            ),
            rolling_item_seconds=12.5,
            available_slots=4,
        )
        snapshot = await reader.snapshot()
        assert snapshot.depth == 10
        assert snapshot.rolling_item_seconds == 12.5
        assert snapshot.available_slots == 4

    asyncio.run(run())


def test_queue_metadata_failure_is_fail_closed() -> None:
    async def run() -> None:
        reader = RedisQueueSnapshotReader(
            client=_RedisHealthClient(error=ConnectionError("secret host")),
            rolling_item_seconds=10,
            available_slots=2,
        )
        with pytest.raises(RedisUnavailable, match="metadata"):
            await reader.snapshot()

    asyncio.run(run())


def test_health_monitor_records_error_type_without_connection_detail() -> None:
    async def run() -> None:
        state = RedisHealthState(stale_after_seconds=30)
        monitor = RedisHealthMonitor(
            client=_RedisHealthClient(error=ConnectionError("redis://secret")),
            state=state,
            interval_seconds=1,
        )
        await monitor.check_once()
        with pytest.raises(RedisUnavailable) as error:
            state.require_available(now=0)
        assert "ConnectionError" in str(error.value)
        assert "secret" not in str(error.value)

    asyncio.run(run())


class _Uploads:
    async def load(self, upload_id: str) -> tuple[bytes, str]:
        return f"upload:{upload_id}".encode(), "image/png"


class _Images:
    async def load(self, image_key: str) -> bytes:
        return f"generated:{image_key}".encode()


class _Signer:
    def upload_url(self, upload_id: str) -> str:
        return f"https://uploads.invalid/{upload_id}"

    def generated_url(self, image_key: str) -> str:
        return f"https://generated.invalid/{image_key}"


def _work_with_references() -> GenerationWorkItem:
    spec = GenerationItemSpec(
        item_id="item-1",
        operation_id="operation-1",
        sequence=1,
        image_type=None,
        operation_type=OperationType.EDIT_IMAGE,
        render_tier=RenderTier.STANDARD,
        final_prompt="edit product",
        model=ModelName.GPT_IMAGE_2,
        ratio="1:1",
        size=(1024, 1024),
        quality=None,
        seed=0,
        references=(
            ReferenceSnapshot(
                source=ReferenceSource.GENERATED,
                object_key="source.png",
                role="source",
                order=1,
            ),
            ReferenceSnapshot(
                source=ReferenceSource.UPLOAD,
                object_key="product.png",
                role="product",
                order=0,
            ),
        ),
        reserved_cost=Decimal("0.05"),
    )
    return GenerationWorkItem(
        job_id="job-1",
        user_id="user-1",
        spec=spec,
        status=GenerationItemStatus.QUEUED,
        provider_task_id=None,
        worker_id=None,
    )


def test_reference_materializer_orders_and_selects_bytes_or_urls() -> None:
    async def run() -> None:
        materializer = StoredReferenceMaterializer(
            uploads=_Uploads(),  # type: ignore[arg-type]
            images=_Images(),  # type: ignore[arg-type]
            signer=_Signer(),  # type: ignore[arg-type]
        )
        work = _work_with_references()

        byte_refs = await materializer.materialize(work, "bytes")
        assert [reference.data for reference in byte_refs] == [
            b"upload:product.png",
            b"generated:source.png",
        ]

        url_refs = await materializer.materialize(work, "url")
        assert [reference.url for reference in url_refs] == [
            "https://uploads.invalid/product.png",
            "https://generated.invalid/source.png",
        ]

    asyncio.run(run())
