"""生产 ASGI 应用：lifespan 装配真实基础设施（MySQL；listing 异步出图+SSE 单进程，无 Redis）。

运行：`uv run uvicorn design_hub.interface.api.asgi:app`（需 DB_URL 指向真实 MySQL）。
2026-06-12 世界 A（客户/接单流）整体移除（ISSUE-0046，纯 toC 自助出图）：
仅保留 listing 一键出图主线 + 模型配置/用户管理 + 认证。
"""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import timedelta

from fastapi import Depends, FastAPI

from design_hub.application.admin.model_config_service import ModelConfigService
from design_hub.application.admin.user_admin_service import UserAdminService
from design_hub.application.auth.account_service import AccountService
from design_hub.application.chat.orchestrator import ChatOrchestrator
from design_hub.application.chat.session_store import InMemorySessionStore
from design_hub.application.cost.budget import BudgetPolicy
from design_hub.application.cost.guard import CostGuard
from design_hub.application.listing.job_launcher import ListingJobLauncher
from design_hub.application.listing.listing_service import ListingGenerationService
from design_hub.application.listing.prompt_composer import (
    CategoryCardRegistry,
    CloneModeRegistry,
    EditModeRegistry,
    ImageTypeRegistry,
    PromptModifierRegistry,
)
from design_hub.application.listing.upload_service import UploadService
from design_hub.application.rate_limit import UserRateLimiter
from design_hub.composition import (
    build_image_store,
    build_media_signer,
    build_registry,
    build_text_llm,
    build_upload_store,
    default_model_configs,
)
from design_hub.config.settings import Settings
from design_hub.domain.enums import Role
from design_hub.infrastructure.auth.jwt_service import PyJwtTokenService
from design_hub.infrastructure.auth.password import BcryptPasswordHasher
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
from design_hub.interface.api.deps import require_role
from design_hub.interface.api.routes import (
    admin,
    auth,
    chat,
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
    # GPT_IMAGE_2 走真实中转 Provider（需 .env 配 GPT_IMAGE_*），其余模型暂 Mock。
    # REAL_GPT_IMAGE=false（本地/联调）→ 全 Mock 图像，零 API 成本、不触真中转站。
    registry = build_registry(
        settings, real_gpt_image=settings.real_gpt_image, unit_costs=unit_costs
    )
    guard = CostGuard(ledger=ledger, policy=BudgetPolicy())
    # 单进程异步（去 Redis/arq）：同一 InMemoryEventBus 既给 runner 发布、又给 /events 订阅
    app.state.task_queue = InProcessTaskQueue()
    # 计费端点 per-user 频控（安全加固 A-4：5 单/分 + ≤2 in-flight，in-memory 零 Redis）
    app.state.rate_limiter = UserRateLimiter()
    app.state.event_stream = InMemoryEventBus()
    # listing 一键出图主线：纯 prompt 直出 + 品类保真卡，复用 guard/queue/event_bus
    app.state.listing_service = ListingGenerationService(
        registry=registry,
        guard=guard,
        modifier_registry=PromptModifierRegistry(),
        card_registry=CategoryCardRegistry(),
        type_registry=ImageTypeRegistry(),
        clone_registry=CloneModeRegistry(),
        edit_registry=EditModeRegistry(),
        concurrency=settings.listing_concurrency,  # ISSUE-0047 保守降档，settings 可覆盖
    )
    # 二次编辑源图读回（ISSUE-0040）：generate 桶/本地 generated/ 的读取面
    app.state.image_store = build_image_store(settings)
    app.state.listing_history = SqlAlchemyListingHistory(session_factory)
    # 启动扫尾（Finding B）：单进程 asyncio 出图，进程崩/部署撞在飞任务会杀掉未终态的
    # create_task，留永久「生成中」僵尸行（SSE 永久转圈、霸占最近一单）。单进程下启动扫
    # 一次即够（此刻 queue 空、无在飞任务竞争，不需定时任务）。阈值 15 分钟为宽松安全值：
    # 远超 gpt-image edit 实测 ~187s + 套图并发批次余量，绝不误杀滚动部署时旧进程仍在
    # 收尾的真实任务；纯现列 UPDATE，无迁移。
    await app.state.listing_history.reap_stale(
        older_than=timedelta(minutes=15), error="进程重启中断/超时兜底（Finding B）"
    )
    app.state.listing_query = SqlAlchemyListingHistoryQuery(session_factory)
    # 历史/SSE 图 url 签名器（TOS 私有→预签名；本地→/img 静态，ISSUE-0029）
    app.state.media_signer = build_media_signer(settings)
    # 图片上传两步流（ISSUE-0026）：上传图落本地 assets/，预览经 GET /uploads/{id} 代理
    app.state.upload_service = UploadService(store=build_upload_store(settings))
    # 出图启动器（#884⑤ 单一事实源）：listing 路由与 chat orchestrator 共调，
    # 频控/owner 隔离/成本守卫/卡链全在此链内继承。
    app.state.job_launcher = ListingJobLauncher(
        service=app.state.listing_service,
        uploads=app.state.upload_service,
        rate_limiter=app.state.rate_limiter,
        events=app.state.event_stream,
        history=app.state.listing_history,
        queue=app.state.task_queue,
        query=app.state.listing_query,
        image_store=app.state.image_store,
    )
    # 「帮我设计」Agent 对话（方案 C）：复用 job_launcher（频控/owner/成本/卡链全继承）+
    # 同一 event_stream 转发 job 事件 + registry 读 unit_cost（费用确认与工作台同源）。
    # 文本 LLM 未配 key 时用 Mock（探明：现有 key 仅图像权限，文本待用户开）。MVP 会话内存态。
    app.state.chat_orchestrator = ChatOrchestrator(
        text_llm=build_text_llm(settings),
        launcher=app.state.job_launcher,
        event_stream=app.state.event_stream,
        registry=registry,
        sessions=InMemorySessionStore(),
        max_session_jobs=settings.chat_session_max_jobs,
    )
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
    settings = Settings()
    app = FastAPI(
        title="设计中台 · 图生图引擎(async)",
        version="0.1.0",
        lifespan=_lifespan,
        # A-2 纵深：默认/未配 DOCS_ENABLED → 从源头摘除文档三路由（prod 不靠 nginx 也闭）。
        # 前端 codegen 用入库 openapi.json（app.openapi() 离线再生），不受影响。
        docs_url="/docs" if settings.docs_enabled else None,
        redoc_url="/redoc" if settings.docs_enabled else None,
        openapi_url="/openapi.json" if settings.docs_enabled else None,
    )
    # 监控（ISSUE-0008）：Sentry 异常接入 + HTTP 指标采集 + 暴露 GET /metrics（不挂鉴权，供裸抓）
    # /metrics 不做 app 层开关：内网抓取直连容器 8000，公网由 nginx 两族 404 收口。
    init_sentry(settings.sentry_dsn)
    instrument_app(app)
    # WP-G 角色矩阵：在 include 级统一挂依赖；/auth 公开；listing/uploads 自带逐路由鉴权
    manager_only = [Depends(require_role(Role.MANAGER))]  # 仅管理者
    app.include_router(auth.router)  # 公开：/auth/register、/auth/login；/me 自带 current_user
    # listing 一键出图主线：鉴权 Bearer + SSE ?access_token=（ISSUE-0011）
    app.include_router(listing.router)
    # 「帮我设计」Agent 对话入口（方案 C）：POST /chat/messages + /chat/confirm，Bearer 头鉴权
    app.include_router(chat.router)
    # 图片上传两步流（ISSUE-0026）：POST /uploads + GET /uploads/{id} 预览代理
    app.include_router(uploads.router)
    # 仅管理者：模型配置 + 用户管理
    app.include_router(admin.router, dependencies=manager_only)
    app.include_router(users.router, dependencies=manager_only)
    register_error_handlers(app)
    return app


app = create_production_app()
