"""arq worker：消费出图队列，用 DB-backed ledger + 持久化 + Redis 事件发布执行任务。

运行：`uv run arq design_hub.infrastructure.queue.worker.WorkerSettings`
（需 DB_URL / REDIS_URL 环境变量指向真实 MySQL / Redis）。
"""

from typing import Any

from arq.connections import RedisSettings

from design_hub.application.cost.budget import BudgetPolicy
from design_hub.application.cost.estimator import CostEstimator
from design_hub.application.cost.guard import CostGuard
from design_hub.application.pipeline import GenerationPipeline
from design_hub.application.routing.router import ModelRouter
from design_hub.application.task_runner import GenerationTaskRunner
from design_hub.composition import build_mock_registry, build_orchestrator
from design_hub.config.settings import Settings
from design_hub.infrastructure.db.job_repository import SqlAlchemyJobRepository
from design_hub.infrastructure.db.session import create_engine, create_session_factory
from design_hub.infrastructure.events.redis_bus import RedisEventBus
from design_hub.infrastructure.ledger.sqlalchemy_ledger import SqlAlchemyLedgerRepository
from design_hub.infrastructure.queue.payload import payload_to_brief


async def run_generation(ctx: dict[str, Any], payload: dict[str, Any]) -> str:
    runner: GenerationTaskRunner = ctx["runner"]
    brief = payload_to_brief(payload["brief"])
    return await runner.run(job_id=payload["job_id"], brief=brief, user_id=payload["user_id"])


async def startup(ctx: dict[str, Any]) -> None:
    settings = Settings()
    db = create_engine(settings.db_url)
    session_factory = create_session_factory(db)
    ledger = SqlAlchemyLedgerRepository(session_factory)
    pipeline = GenerationPipeline(
        router=ModelRouter(),
        orchestrator=build_orchestrator(),
        registry=build_mock_registry(),
        estimator=CostEstimator(),
        guard=CostGuard(ledger=ledger, policy=BudgetPolicy()),
    )
    events = RedisEventBus.from_url(settings.redis_url)
    ctx["runner"] = GenerationTaskRunner(
        pipeline=pipeline,
        jobs=SqlAlchemyJobRepository(session_factory),
        events=events,
    )
    ctx["_db"] = db
    ctx["_events"] = events


async def shutdown(ctx: dict[str, Any]) -> None:
    await ctx["_db"].dispose()
    await ctx["_events"].aclose()


class WorkerSettings:
    functions = [run_generation]
    on_startup = startup
    on_shutdown = shutdown
    redis_settings = RedisSettings.from_dsn(Settings().redis_url)
