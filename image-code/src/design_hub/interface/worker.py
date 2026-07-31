import asyncio
import os
import re
import signal
import socket
from typing import cast

from redis.asyncio import Redis

from design_hub.application.listing.upload_service import UploadService
from design_hub.application.tasking.outbox_dispatcher import OutboxDispatcher
from design_hub.application.tasking.runtime import GenerationWorkerRuntime
from design_hub.application.tasking.worker import GenerationWorker
from design_hub.composition import (
    build_image_store,
    build_media_signer,
    build_secret_cipher,
    build_upload_store,
)
from design_hub.config.settings import Settings
from design_hub.domain.tasking import RenderTier
from design_hub.infrastructure.db.generation_work_repo import (
    SqlAlchemyGenerationWorkRepository,
)
from design_hub.infrastructure.db.model_call_repo import SqlAlchemyModelCallRecorder
from design_hub.infrastructure.db.model_config_repo import (
    SqlAlchemyModelConfigRepository,
)
from design_hub.infrastructure.db.session import (
    create_engine,
    create_session_factory,
)
from design_hub.infrastructure.monitoring.logging import configure_logging
from design_hub.infrastructure.monitoring.setup import init_sentry
from design_hub.infrastructure.providers.live_resolution import (
    LiveImageExecutorResolver,
)
from design_hub.infrastructure.queue.redis_slots import RedisEvalClient, RedisProviderSlots
from design_hub.infrastructure.queue.redis_streams import (
    RedisJobEventStream,
    RedisStreamClient,
    RedisTaskBroker,
)
from design_hub.infrastructure.storage.reference_materializer import (
    StoredReferenceMaterializer,
)
from design_hub.ports.events import EventPublisher

_SAFE_WORKER_ID = re.compile(r"[^A-Za-z0-9._-]")


def _worker_id() -> str:
    raw = f"{socket.gethostname()}-{os.getpid()}"
    return _SAFE_WORKER_ID.sub("-", raw)[:128]


async def run_worker(settings: Settings | None = None) -> None:
    settings = settings or Settings()
    cipher = build_secret_cipher(settings)
    configure_logging(
        runtime_log_dir=settings.runtime_log_dir,
        service="worker",
        runtime_log_max_bytes=settings.runtime_log_max_bytes,
    )
    init_sentry(settings.sentry_dsn)
    engine = create_engine(settings.db_url)
    session_factory = create_session_factory(engine)
    model_config_repo = SqlAlchemyModelConfigRepository(session_factory)
    recorder = SqlAlchemyModelCallRecorder(session_factory)
    redis = Redis.from_url(settings.redis_url, decode_responses=True)
    stream_client = cast(RedisStreamClient, redis)
    eval_client = cast(RedisEvalClient, redis)
    repository = SqlAlchemyGenerationWorkRepository(session_factory)
    broker = RedisTaskBroker(stream_client)
    events = RedisJobEventStream(stream_client)
    image_store = build_image_store(settings)
    materializer = StoredReferenceMaterializer(
        uploads=UploadService(store=build_upload_store(settings)),
        images=image_store,
        signer=build_media_signer(settings),
    )
    executor_resolver = LiveImageExecutorResolver(
        repository=model_config_repo,
        cipher=cipher,
        recorder=recorder,
        image_store=image_store,
        settings=settings,
    )
    slots: dict[tuple[str, RenderTier], RedisProviderSlots] = {}

    def slots_for(model: str, tier: RenderTier) -> RedisProviderSlots:
        key = (model, tier)
        if key not in slots:
            limit = (
                settings.provider_4k_concurrency
                if tier is RenderTier.FOUR_K
                else settings.provider_standard_concurrency
            )
            slots[key] = RedisProviderSlots(
                client=eval_client,
                provider=model,
                tier=tier.value,
                limit=limit,
                lease_seconds=settings.provider_slot_lease_seconds,
            )
        return slots[key]

    worker_id = _worker_id()
    worker = GenerationWorker(
        repository=repository,
        broker=broker,
        executor_resolver=executor_resolver,
        materializer=materializer,
        slots_for=slots_for,
        worker_id=worker_id,
        lease_seconds=settings.provider_slot_lease_seconds,
        heartbeat_seconds=15,
        slot_refresh_seconds=settings.provider_slot_refresh_seconds,
    )
    runtime = GenerationWorkerRuntime(
        dispatcher=OutboxDispatcher(
            repository=repository,
            broker=broker,
            events=cast(EventPublisher, events),
            batch_size=settings.outbox_batch_size,
        ),
        broker=broker,
        worker=worker,
        consumer_name=worker_id,
        read_count=settings.worker_read_count,
        read_block_ms=settings.worker_read_block_ms,
        reclaim_idle_ms=settings.worker_reclaim_idle_ms,
        dispatcher_interval_seconds=settings.worker_dispatch_interval_seconds,
        shutdown_timeout_seconds=settings.worker_shutdown_timeout_seconds,
    )
    stop = asyncio.Event()
    loop = asyncio.get_running_loop()
    for signum in (signal.SIGTERM, signal.SIGINT):
        loop.add_signal_handler(signum, stop.set)
    try:
        await runtime.run(stop)
    finally:
        await redis.aclose()
        await engine.dispose()


def main() -> None:
    asyncio.run(run_worker())


if __name__ == "__main__":
    main()
