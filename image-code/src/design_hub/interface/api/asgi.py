"""生产 ASGI 应用：lifespan 装配真实基础设施（MySQL + Redis + arq）。

运行：`uv run uvicorn design_hub.interface.api.asgi:app`
（需 DB_URL / REDIS_URL 指向真实 MySQL / Redis）。同步与异步端点同时提供。
"""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from arq.connections import RedisSettings, create_pool
from fastapi import Depends, FastAPI

from design_hub.application.admin.model_config_service import ModelConfigService
from design_hub.application.auth.auth_service import AuthService
from design_hub.application.cost.budget import BudgetPolicy
from design_hub.application.cost.estimator import CostEstimator
from design_hub.application.cost.guard import CostGuard
from design_hub.application.cost.preview import CostPreviewService
from design_hub.application.dashboard.cost_report import CostReportService
from design_hub.application.export.export_service import ExportService
from design_hub.application.pipeline import GenerationPipeline
from design_hub.application.project.asset_service import AssetService
from design_hub.application.project.brief_service import BriefService
from design_hub.application.project.customer_service import CustomerService
from design_hub.application.project.project_generation_service import (
    ProjectGenerationService,
)
from design_hub.application.project.project_service import ProjectService
from design_hub.application.revision.revision_service import RevisionService
from design_hub.application.routing.router import ModelRouter
from design_hub.application.selection.selection_service import SelectionService
from design_hub.composition import (
    Engine,
    build_orchestrator,
    build_registry,
    default_model_configs,
)
from design_hub.config.settings import Settings
from design_hub.domain.enums import Role
from design_hub.infrastructure.auth.jwt_service import PyJwtTokenService
from design_hub.infrastructure.auth.mock_oauth import MockOAuthClient
from design_hub.infrastructure.db.asset_repo import SqlAlchemyAssetRepository
from design_hub.infrastructure.db.brief_repo import SqlAlchemyBriefRepository
from design_hub.infrastructure.db.cost_query import SqlAlchemyCostQuery
from design_hub.infrastructure.db.customer_repo import SqlAlchemyCustomerRepository
from design_hub.infrastructure.db.export_query import SqlAlchemyExportQuery
from design_hub.infrastructure.db.image_repo import SqlAlchemyGeneratedImageRepository
from design_hub.infrastructure.db.job_repository import SqlAlchemyJobRepository
from design_hub.infrastructure.db.model_config_repo import SqlAlchemyModelConfigRepository
from design_hub.infrastructure.db.project_repo import SqlAlchemyProjectRepository
from design_hub.infrastructure.db.revision_repo import SqlAlchemyRevisionRepository
from design_hub.infrastructure.db.session import create_engine, create_session_factory
from design_hub.infrastructure.events.redis_bus import RedisEventBus
from design_hub.infrastructure.export.local_export_store import LocalExportStore
from design_hub.infrastructure.export.pillow_exporter import PillowExporter
from design_hub.infrastructure.ledger.sqlalchemy_ledger import SqlAlchemyLedgerRepository
from design_hub.infrastructure.queue.arq_queue import ArqTaskQueue
from design_hub.infrastructure.storage.local_asset import LocalAssetStore
from design_hub.interface.api.app import register_error_handlers
from design_hub.interface.api.deps import get_current_user, require_role
from design_hub.interface.api.routes import (
    admin,
    async_generation,
    auth,
    brief,
    customers,
    dashboard,
    export,
    generation,
    projects,
    revision,
    selection,
)


@asynccontextmanager
async def _lifespan(app: FastAPI) -> AsyncIterator[None]:
    settings = Settings()
    db = create_engine(settings.db_url)
    session_factory = create_session_factory(db)
    ledger = SqlAlchemyLedgerRepository(session_factory)
    router = ModelRouter()
    estimator = CostEstimator()
    # WP-H 模型配置后台：seed 默认 5 模型(仅插缺失) + 读 DB 真实单价注入 registry(缺失回落 Mock)
    model_config_repo = SqlAlchemyModelConfigRepository(session_factory)
    model_config_service = ModelConfigService(repo=model_config_repo)
    await model_config_service.seed_defaults(default_model_configs())
    unit_costs = await model_config_service.unit_cost_map()
    # GPT_IMAGE_2 走真实中转 Provider（需 .env 配 GPT_IMAGE_*），其余模型暂 Mock
    registry = build_registry(settings, real_gpt_image=True, unit_costs=unit_costs)
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
    # WP-A 工作台：客户/项目用例（DB-backed）
    customer_repo = SqlAlchemyCustomerRepository(session_factory)
    project_repo = SqlAlchemyProjectRepository(session_factory)
    revision_repo = SqlAlchemyRevisionRepository(session_factory)
    app.state.customer_service = CustomerService(customers=customer_repo)
    # WP-D：ProjectService 注入 revision_repo，转「已交付」做交付强校验
    app.state.project_service = ProjectService(
        projects=project_repo, customers=customer_repo, revisions=revision_repo
    )
    # WP-B 标准化需求单 + 素材上传 + 项目下出图（挂 project_id+round_no，复用 pipeline）
    brief_repo = SqlAlchemyBriefRepository(session_factory)
    asset_repo = SqlAlchemyAssetRepository(session_factory)
    asset_store = LocalAssetStore(settings.asset_output_dir)
    app.state.brief_service = BriefService(briefs=brief_repo, projects=project_repo)
    app.state.asset_service = AssetService(
        assets=asset_repo, store=asset_store, projects=project_repo
    )
    app.state.project_generation_service = ProjectGenerationService(
        projects=project_repo, customers=customer_repo, briefs=brief_repo,
        assets=asset_repo, store=asset_store, pipeline=pipeline,
        jobs=SqlAlchemyJobRepository(session_factory),
    )
    # WP-F 成本仪表盘：5 维聚合查询用例（纯读 DB）
    app.state.cost_report_service = CostReportService(query=SqlAlchemyCostQuery(session_factory))
    # WP-C 选稿+评分：候选图打分/保留 + 任务可用率（DB-backed）
    app.state.selection_service = SelectionService(
        images=SqlAlchemyGeneratedImageRepository(session_factory)
    )
    # WP-H 模型配置后台：ModelConfig CRUD + 单价热更（已 seed/注入，见上）
    app.state.model_config_service = model_config_service
    # WP-E 导出归档：多格式/改尺寸/zip + 命名规范 + 项目/子场景/轮次 归档（本地落点）
    app.state.export_service = ExportService(
        query=SqlAlchemyExportQuery(session_factory),
        exporter=PillowExporter(),
        store=LocalExportStore(settings.export_output_dir),
    )
    # WP-D 改稿单：开单/列单/加条目/逐条勾选（交付强校验经 ProjectService.revisions）
    app.state.revision_service = RevisionService(revisions=revision_repo, projects=project_repo)
    # WP-G 鉴权：JWT 令牌服务 + （mock）OAuth 登录用例（真实飞书/钉钉待用户给凭据）
    token_service = PyJwtTokenService(
        secret=settings.jwt_secret.get_secret_value(), ttl_hours=settings.jwt_ttl_hours
    )
    app.state.token_service = token_service
    app.state.auth_service = AuthService(oauth=MockOAuthClient(), tokens=token_service)
    try:
        yield
    finally:
        await db.dispose()
        await pool.aclose()
        await stream.aclose()


def create_production_app() -> FastAPI:
    app = FastAPI(title="设计中台 · 图生图引擎(async)", version="0.1.0", lifespan=_lifespan)
    # WP-G 角色矩阵：在 include 级统一挂依赖（减少逐函数改动）；/auth 公开
    login_required = [Depends(get_current_user)]  # 登录即可：设计师 + 管理者
    manager_only = [Depends(require_role(Role.MANAGER))]  # 仅管理者
    app.include_router(auth.router)  # 公开：/auth/{provider}/callback；/me 自带 current_user
    # 需登录（设计师本人/全量过滤待 ISSUE-0006 加 owner 列后细化）
    app.include_router(generation.router, dependencies=login_required)
    app.include_router(async_generation.router, dependencies=login_required)
    app.include_router(customers.router, dependencies=login_required)
    app.include_router(projects.router, dependencies=login_required)
    app.include_router(brief.router, dependencies=login_required)
    app.include_router(selection.router, dependencies=login_required)
    app.include_router(export.router, dependencies=login_required)
    app.include_router(revision.router, dependencies=login_required)
    # 仅管理者：成本仪表盘 + 模型配置
    app.include_router(dashboard.router, dependencies=manager_only)
    app.include_router(admin.router, dependencies=manager_only)
    register_error_handlers(app)
    return app


app = create_production_app()
