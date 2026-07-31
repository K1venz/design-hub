"""Production API process: admission, durable submission, query, and SSE only.

Provider execution belongs exclusively to ``design_hub.interface.worker``.
"""

import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import cast

from fastapi import Depends, FastAPI
from redis.asyncio import Redis

from design_hub.application.admin.admin_console_service import AdminConsoleService
from design_hub.application.admin.model_capability_service import (
    LiveCapabilityProviderFactory,
    ModelCapabilityService,
)
from design_hub.application.admin.model_config_service import ModelConfigService
from design_hub.application.admin.runtime_log_service import RuntimeLogService
from design_hub.application.admin.user_admin_service import UserAdminService
from design_hub.application.auth.account_service import AccountService
from design_hub.application.chat.orchestrator import ChatOrchestrator
from design_hub.application.chat.pending_store import PendingStore
from design_hub.application.image_prompts.reverse_prompt import (
    ReversePromptService,
)
from design_hub.application.listing.prompt_composer import (
    CategoryCardRegistry,
    CloneModeRegistry,
    EditModeRegistry,
    ImageTypeRegistry,
    PromptModifierRegistry,
)
from design_hub.application.listing.submission_service import (
    ListingSubmissionService,
)
from design_hub.application.listing.task_planner import ListingTaskPlanner
from design_hub.application.listing.upload_service import UploadService
from design_hub.application.tasking.health import (
    QueueAdmissionController,
    RedisHealthState,
)
from design_hub.composition import (
    build_image_store,
    build_media_signer,
    build_secret_cipher,
    build_upload_store,
)
from design_hub.config.settings import Settings
from design_hub.domain.enums import Role
from design_hub.infrastructure.auth.jwt_service import PyJwtTokenService
from design_hub.infrastructure.auth.password import BcryptPasswordHasher
from design_hub.infrastructure.db.admin_console_repo import (
    SqlAlchemyAdminConsoleRepository,
)
from design_hub.infrastructure.db.chat_repo import SqlAlchemyChatSessionRepository
from design_hub.infrastructure.db.generation_work_repo import (
    SqlAlchemyGenerationWorkRepository,
)
from design_hub.infrastructure.db.listing_query_repo import SqlAlchemyListingHistoryQuery
from design_hub.infrastructure.db.model_call_repo import SqlAlchemyModelCallRecorder
from design_hub.infrastructure.db.model_config_repo import SqlAlchemyModelConfigRepository
from design_hub.infrastructure.db.session import create_engine, create_session_factory
from design_hub.infrastructure.db.user_repo import SqlAlchemyUserRepository
from design_hub.infrastructure.monitoring.logging import (
    configure_logging,
    install_request_context,
)
from design_hub.infrastructure.monitoring.runtime_log_files import (
    FileRuntimeLogRepository,
)
from design_hub.infrastructure.monitoring.setup import init_sentry, instrument_app
from design_hub.infrastructure.providers.live_resolution import (
    LiveTextLLMResolver,
)
from design_hub.infrastructure.queue.redis_health import (
    RedisHealthClient,
    RedisHealthMonitor,
    RedisQueueSnapshotReader,
)
from design_hub.infrastructure.queue.redis_streams import (
    RedisJobEventStream,
    RedisStreamClient,
)
from design_hub.infrastructure.security.model_verification import PyJwtModelVerificationService
from design_hub.interface.api.app import register_error_handlers
from design_hub.interface.api.deps import require_role
from design_hub.interface.api.routes import (
    admin,
    admin_console,
    auth,
    chat,
    image_prompts,
    listing,
    models,
    runtime_logs,
    showcase,
    uploads,
    users,
)


@asynccontextmanager
async def _lifespan(app: FastAPI) -> AsyncIterator[None]:
    settings = Settings()
    app.state.runtime_log_service = RuntimeLogService(
        FileRuntimeLogRepository(settings.runtime_log_dir)
    )
    app.state.secret_cipher = build_secret_cipher(settings)
    db = create_engine(settings.db_url)
    session_factory = create_session_factory(db)
    model_call_recorder = SqlAlchemyModelCallRecorder(session_factory)
    model_config_repo = SqlAlchemyModelConfigRepository(session_factory)
    verifier = PyJwtModelVerificationService(
        secret=settings.jwt_secret.get_secret_value(),
        ttl_seconds=settings.model_verification_ttl_seconds,
    )
    model_config_service = ModelConfigService(
        repo=model_config_repo,
        cipher=app.state.secret_cipher,
        verifier=verifier,
    )
    planner = ListingTaskPlanner(
        modifier_registry=PromptModifierRegistry(),
        card_registry=CategoryCardRegistry(),
        type_registry=ImageTypeRegistry(),
        clone_registry=CloneModeRegistry(),
        edit_registry=EditModeRegistry(),
    )
    app.state.listing_query = SqlAlchemyListingHistoryQuery(session_factory)
    app.state.media_signer = build_media_signer(settings)
    app.state.upload_service = UploadService(store=build_upload_store(settings))
    image_store = build_image_store(settings)
    text_llm_resolver = LiveTextLLMResolver(
        repository=model_config_repo,
        cipher=app.state.secret_cipher,
        recorder=model_call_recorder,
        settings=settings,
    )
    app.state.reverse_prompt_service = ReversePromptService(
        text_llm_resolver=text_llm_resolver,
        uploads=app.state.upload_service,
        images=image_store,
        query=app.state.listing_query,
    )

    redis = Redis.from_url(settings.redis_url, decode_responses=True)
    redis_health = RedisHealthState(stale_after_seconds=settings.redis_health_stale_seconds)
    health_client = cast(RedisHealthClient, redis)
    stream_client = cast(RedisStreamClient, redis)
    health_monitor = RedisHealthMonitor(
        client=health_client,
        state=redis_health,
        interval_seconds=settings.redis_health_interval_seconds,
    )
    await health_monitor.check_once()
    health_stop = asyncio.Event()
    health_task = asyncio.create_task(health_monitor.run(health_stop))
    app.state.event_stream = RedisJobEventStream(stream_client)
    app.state.listing_submission = ListingSubmissionService(
        planner=planner,
        repository=SqlAlchemyGenerationWorkRepository(session_factory),
        query=app.state.listing_query,
        uploads=app.state.upload_service,
        redis_health=redis_health,
        queue_snapshots=RedisQueueSnapshotReader(
            client=health_client,
            rolling_item_seconds=settings.queue_rolling_item_seconds,
            available_slots=(
                settings.provider_standard_concurrency + settings.provider_4k_concurrency
            ),
        ),
        admission=QueueAdmissionController(
            soft_wait_seconds=settings.queue_soft_wait_seconds,
            confirm_wait_seconds=settings.queue_confirm_wait_seconds,
            hard_depth=settings.queue_hard_depth,
        ),
        model_configs=model_config_repo,
    )

    app.state.chat_repo = SqlAlchemyChatSessionRepository(session_factory)
    app.state.chat_orchestrator = ChatOrchestrator(
        text_llm_resolver=text_llm_resolver,
        submission=app.state.listing_submission,
        event_stream=app.state.event_stream,
        uploads=app.state.upload_service,
        chat_repo=app.state.chat_repo,
        pending=PendingStore(),
        query=app.state.listing_query,
        model_config=model_config_repo,
        reverse_prompt=app.state.reverse_prompt_service,
        max_session_jobs=settings.chat_session_max_jobs,
    )
    app.state.model_config_service = model_config_service
    app.state.model_capability_service = ModelCapabilityService(
        repository=model_config_repo,
        cipher=app.state.secret_cipher,
        verifier=verifier,
        providers=LiveCapabilityProviderFactory(
            recorder=model_call_recorder,
            settings=settings,
        ),
    )
    app.state.admin_console_service = AdminConsoleService(
        repository=SqlAlchemyAdminConsoleRepository(session_factory)
    )
    token_service = PyJwtTokenService(
        secret=settings.jwt_secret.get_secret_value(),
        ttl_hours=settings.jwt_ttl_hours,
        renew_after_hours=settings.jwt_renew_after_hours,
    )
    app.state.token_service = token_service
    user_repo = SqlAlchemyUserRepository(session_factory)
    account_service = AccountService(
        users=user_repo,
        passwords=BcryptPasswordHasher(),
        tokens=token_service,
    )
    if settings.seed_admin_email and settings.seed_admin_password.get_secret_value():
        await account_service.seed_admin(
            email=settings.seed_admin_email,
            password=settings.seed_admin_password.get_secret_value(),
        )
    app.state.account_service = account_service
    app.state.user_repository = user_repo
    app.state.user_admin_service = UserAdminService(users=user_repo)
    try:
        yield
    finally:
        health_stop.set()
        await health_task
        await redis.aclose()
        await db.dispose()


def create_production_app() -> FastAPI:
    settings = Settings()
    configure_logging(
        runtime_log_dir=settings.runtime_log_dir,
        service="api",
        runtime_log_max_bytes=settings.runtime_log_max_bytes,
    )
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
    install_request_context(app)
    # WP-G 角色矩阵：在 include 级统一挂依赖；/auth 公开；listing/uploads 自带逐路由鉴权
    manager_only = [Depends(require_role(Role.MANAGER))]  # 仅管理者
    app.include_router(auth.router)  # 公开：/auth/register、/auth/login；/me 自带 current_user
    # listing 一键出图主线：鉴权 Bearer + SSE ?access_token=（ISSUE-0011）
    app.include_router(listing.router)
    app.include_router(image_prompts.router)
    # 「帮我设计」Agent 对话入口（方案 C）：POST /chat/messages + /chat/confirm，Bearer 头鉴权
    app.include_router(chat.router)
    # 图片上传两步流（ISSUE-0026）：POST /uploads + GET /uploads/{id} 预览代理
    app.include_router(uploads.router)
    # 公开首页成果展示（无鉴权）：精选清单现签 url，无用户数据/prompt 泄漏
    app.include_router(showcase.router)
    app.include_router(models.router)
    # 仅管理者：模型配置 + 用户管理
    app.include_router(admin.router, dependencies=manager_only)
    app.include_router(admin_console.router, dependencies=manager_only)
    app.include_router(runtime_logs.router, dependencies=manager_only)
    app.include_router(users.router, dependencies=manager_only)
    register_error_handlers(app)
    return app


app = create_production_app()
