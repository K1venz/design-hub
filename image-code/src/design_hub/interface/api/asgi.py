"""生产 ASGI 应用：lifespan 装配真实基础设施（MySQL + Redis + arq）。

运行：`uv run uvicorn design_hub.interface.api.asgi:app`
（需 DB_URL / REDIS_URL 指向真实 MySQL / Redis）。同步与异步端点同时提供。
"""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from arq.connections import RedisSettings, create_pool
from fastapi import FastAPI

from design_hub.application.cost.budget import BudgetPolicy
from design_hub.application.cost.estimator import CostEstimator
from design_hub.application.cost.guard import CostGuard
from design_hub.application.cost.preview import CostPreviewService
from design_hub.application.pipeline import GenerationPipeline
from design_hub.application.routing.router import ModelRouter
from design_hub.composition import Engine, build_orchestrator, build_registry
from design_hub.config.settings import Settings
from design_hub.infrastructure.db.session import create_engine, create_session_factory
from design_hub.infrastructure.events.redis_bus import RedisEventBus
from design_hub.infrastructure.ledger.sqlalchemy_ledger import SqlAlchemyLedgerRepository
from design_hub.infrastructure.queue.arq_queue import ArqTaskQueue
from design_hub.interface.api.app import register_error_handlers
from design_hub.interface.api.routes import async_generation, generation


@asynccontextmanager
async def _lifespan(app: FastAPI) -> AsyncIterator[None]:
    settings = Settings()
    db = create_engine(settings.db_url)
    session_factory = create_session_factory(db)
    ledger = SqlAlchemyLedgerRepository(session_factory)
    router = ModelRouter()
    estimator = CostEstimator()
    # GPT_IMAGE_2 走真实中转 Provider（需 .env 配 GPT_IMAGE_*），其余模型暂 Mock
    registry = build_registry(settings, real_gpt_image=True)
    pipeline = GenerationPipeline(
        router=router,
        orchestrator=build_orchestrator(),
        registry=registry,
        estimator=estimator,
        guard=CostGuard(ledger=ledger, policy=BudgetPolicy()),
    )
    preview = CostPreviewService(
        router=router, registry=registry, estimator=estimator, ledger=ledger
    )
    pool = await create_pool(RedisSettings.from_dsn(settings.redis_url))
    stream = RedisEventBus.from_url(settings.redis_url)

    app.state.engine = Engine(pipeline=pipeline, preview=preview)
    app.state.task_queue = ArqTaskQueue(pool)
    app.state.event_stream = stream
    try:
        yield
    finally:
        await db.dispose()
        await pool.aclose()
        await stream.aclose()


def create_production_app() -> FastAPI:
    app = FastAPI(title="设计中台 · 图生图引擎(async)", version="0.1.0", lifespan=_lifespan)
    app.include_router(generation.router)
    app.include_router(async_generation.router)
    register_error_handlers(app)
    return app


app = create_production_app()
