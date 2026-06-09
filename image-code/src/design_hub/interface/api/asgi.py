"""生产 ASGI 应用：lifespan 装配真实基础设施（MySQL；listing 异步出图+SSE 单进程，无 Redis）。

运行：`uv run uvicorn design_hub.interface.api.asgi:app`（需 DB_URL 指向真实 MySQL）。
2026-06-09 旧海报/项目/单图出图流已下线（ISSUE-0039：去 legacy + 消可伪造 X-User-Id 归属漏洞），
仅保留 listing 一键出图主线 + 客户档案 + 成本仪表盘/模型配置/用户管理 + 认证。
"""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI

from design_hub.application.admin.model_config_service import ModelConfigService
from design_hub.application.admin.user_admin_service import UserAdminService
from design_hub.application.auth.account_service import AccountService
from design_hub.application.cost.budget import BudgetPolicy
from design_hub.application.cost.guard import CostGuard
from design_hub.application.dashboard.cost_report import CostReportService
from design_hub.application.listing.listing_service import ListingGenerationService
from design_hub.application.listing.prompt_composer import (
    CategoryCardRegistry,
    PromptModifierRegistry,
)
from design_hub.application.listing.upload_service import UploadService
from design_hub.application.project.customer_service import CustomerService
from design_hub.composition import (
    build_media_signer,
    build_registry,
    build_upload_store,
    default_model_configs,
)
from design_hub.config.settings import Settings
from design_hub.domain.enums import Role
from design_hub.infrastructure.auth.jwt_service import PyJwtTokenService
from design_hub.infrastructure.auth.password import BcryptPasswordHasher
from design_hub.infrastructure.db.cost_query import SqlAlchemyCostQuery
from design_hub.infrastructure.db.customer_repo import SqlAlchemyCustomerRepository
from design_hub.infrastructure.db.listing_history_repo import SqlAlchemyListingHistory
from design_hub.infrastructure.db.listing_query_repo import SqlAlchemyListingHistoryQuery
from design_hub.infrastructure.db.model_config_repo import SqlAlchemyModelConfigRepository
from design_hub.infrastructure.db.session import create_engine, create_session_factory
from design_hub.infrastructure.db.user_repo import SqlAlchemyUserRepository
from design_hub.infrastructure.events.memory import InMemoryEventBus
from design_hub.infrastructure.ledger.sqlalchemy_ledger import SqlAlchemyLedgerRepository
from design_hub.infrastructure.monitoring.setup import init_sentry, instrument_app
from design_hub.infrastructure.queue.in_process import InProcessTaskQueue
from design_hub.interface.api.app import register_error_handlers
from design_hub.interface.api.deps import get_current_user, require_role
from design_hub.interface.api.routes import (
    admin,
    auth,
    customers,
    dashboard,
    listing,
    uploads,
    users,
)


@asynccontextmanager
async def _lifespan(app: FastAPI) -> AsyncIterator[None]:
    settings = Settings()
    db = create_engine(settings.db_url)
    session_factory = create_session_factory(db)
    ledger = SqlAlchemyLedgerRepository(session_factory)
    # WP-H 模型配置后台：seed 默认模型(仅插缺失) + 读 DB 真实单价注入 registry(缺失回落 Mock)
    model_config_repo = SqlAlchemyModelConfigRepository(session_factory)
    model_config_service = ModelConfigService(repo=model_config_repo)
    await model_config_service.seed_defaults(default_model_configs())
    unit_costs = await model_config_service.unit_cost_map()
    # GPT_IMAGE_2 走真实中转 Provider（需 .env 配 GPT_IMAGE_*），其余模型暂 Mock
    registry = build_registry(settings, real_gpt_image=True, unit_costs=unit_costs)
    guard = CostGuard(ledger=ledger, policy=BudgetPolicy())
    # 单进程异步（去 Redis/arq）：同一 InMemoryEventBus 既给 runner 发布、又给 /events 订阅
    app.state.task_queue = InProcessTaskQueue()
    app.state.event_stream = InMemoryEventBus()
    # listing 一键出图主线：纯 prompt 直出 + 品类保真卡，复用 guard/queue/event_bus
    app.state.listing_service = ListingGenerationService(
        registry=registry,
        guard=guard,
        modifier_registry=PromptModifierRegistry(),
        card_registry=CategoryCardRegistry(),
    )
    app.state.listing_history = SqlAlchemyListingHistory(session_factory)
    app.state.listing_query = SqlAlchemyListingHistoryQuery(session_factory)
    # 历史/SSE 图 url 签名器（TOS 私有→预签名；本地→/img 静态，ISSUE-0029）
    app.state.media_signer = build_media_signer(settings)
    # 图片上传两步流（ISSUE-0026）：上传图落本地 assets/，预览经 GET /uploads/{id} 代理
    app.state.upload_service = UploadService(store=build_upload_store(settings))
    # 客户档案（轻量 CRUD，独立于已下线的项目流，保留）
    app.state.customer_service = CustomerService(
        customers=SqlAlchemyCustomerRepository(session_factory)
    )
    # 成本仪表盘：5 维聚合查询用例（纯读 DB）
    app.state.cost_report_service = CostReportService(query=SqlAlchemyCostQuery(session_factory))
    app.state.model_config_service = model_config_service
    # 鉴权（WP-G/ISSUE-0015）：JWT 令牌服务 + 自建邮箱密码认证
    token_service = PyJwtTokenService(
        secret=settings.jwt_secret.get_secret_value(), ttl_hours=settings.jwt_ttl_hours
    )
    app.state.token_service = token_service
    user_repo = SqlAlchemyUserRepository(session_factory)
    account_service = AccountService(
        users=user_repo, passwords=BcryptPasswordHasher(), tokens=token_service
    )
    # 启动幂等 seed 管理员（邮箱/密码走 .env，未配则不 seed）
    if settings.seed_admin_email and settings.seed_admin_password.get_secret_value():
        await account_service.seed_admin(
            email=settings.seed_admin_email,
            password=settings.seed_admin_password.get_secret_value(),
        )
    app.state.account_service = account_service
    app.state.user_admin_service = UserAdminService(users=user_repo)
    try:
        yield
    finally:
        await db.dispose()


def create_production_app() -> FastAPI:
    app = FastAPI(title="设计中台 · 图生图引擎(async)", version="0.1.0", lifespan=_lifespan)
    # 监控（ISSUE-0008）：Sentry 异常接入 + HTTP 指标采集 + 暴露 GET /metrics（不挂鉴权，供裸抓）
    init_sentry(Settings().sentry_dsn)
    instrument_app(app)
    # WP-G 角色矩阵：在 include 级统一挂依赖；/auth 公开
    login_required = [Depends(get_current_user)]  # 登录即可：设计师 + 管理者
    manager_only = [Depends(require_role(Role.MANAGER))]  # 仅管理者
    app.include_router(auth.router)  # 公开：/auth/register、/auth/login；/me 自带 current_user
    # listing 一键出图主线：鉴权 Bearer + SSE ?access_token=（ISSUE-0011）
    app.include_router(listing.router)
    # 图片上传两步流（ISSUE-0026）：POST /uploads + GET /uploads/{id} 预览代理
    app.include_router(uploads.router)
    app.include_router(customers.router, dependencies=login_required)
    # 仅管理者：成本仪表盘 + 模型配置 + 用户管理
    app.include_router(dashboard.router, dependencies=manager_only)
    app.include_router(admin.router, dependencies=manager_only)
    app.include_router(users.router, dependencies=manager_only)
    register_error_handlers(app)
    return app


app = create_production_app()
