from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from design_hub.application.rate_limit import RateLimited
from design_hub.application.tasking.health import (
    AdmissionRejected,
    RedisUnavailable,
)
from design_hub.domain.errors import (
    AuthenticationError,
    BudgetExceeded,
    DomainError,
    NotFoundError,
    PermissionDenied,
)
from design_hub.ports.generation_work import IdempotencyConflict
from design_hub.ports.model_provider import ProviderError


def register_error_handlers(app: FastAPI) -> None:
    """领域/端口错误在边界统一映射为 HTTP（翻译，非吞错）。"""

    @app.exception_handler(BudgetExceeded)
    async def _on_budget(request: Request, exc: BudgetExceeded) -> JSONResponse:
        return JSONResponse(
            status_code=409, content={"error": "budget_exceeded", "detail": exc.reason}
        )

    @app.exception_handler(IdempotencyConflict)
    async def _on_idempotency_conflict(
        request: Request, exc: IdempotencyConflict
    ) -> JSONResponse:
        return JSONResponse(
            status_code=409,
            content={"error": "idempotency_conflict", "detail": str(exc)},
        )

    async def _generation_unavailable(
        request: Request, exc: Exception
    ) -> JSONResponse:
        return JSONResponse(
            status_code=503,
            content={"error": "generation_unavailable", "detail": str(exc)},
            headers={"Retry-After": "30"},
        )

    app.add_exception_handler(RedisUnavailable, _generation_unavailable)
    app.add_exception_handler(AdmissionRejected, _generation_unavailable)

    @app.exception_handler(ProviderError)
    async def _on_provider(request: Request, exc: ProviderError) -> JSONResponse:
        return JSONResponse(
            status_code=502, content={"error": "provider_failed", "detail": str(exc)}
        )

    # 实体不存在（项目/需求单/素材）→ 404；比通用 DomainError(409) 更具体，优先匹配
    @app.exception_handler(NotFoundError)
    async def _on_not_found(request: Request, exc: NotFoundError) -> JSONResponse:
        return JSONResponse(status_code=404, content={"error": "not_found", "detail": str(exc)})

    # 未认证（缺/坏令牌、OAuth 换取失败）→ 401（WP-G）
    @app.exception_handler(AuthenticationError)
    async def _on_unauth(request: Request, exc: AuthenticationError) -> JSONResponse:
        return JSONResponse(
            status_code=401, content={"error": "unauthenticated", "detail": str(exc)}
        )

    # 已认证但角色/部门不许 → 403（WP-G）
    @app.exception_handler(PermissionDenied)
    async def _on_forbidden(request: Request, exc: PermissionDenied) -> JSONResponse:
        return JSONResponse(status_code=403, content={"error": "forbidden", "detail": str(exc)})

    # 通用领域规则违反（如非法状态流转）；BudgetExceeded/NotFoundError 子类有更具体处理
    @app.exception_handler(DomainError)
    async def _on_domain(request: Request, exc: DomainError) -> JSONResponse:
        return JSONResponse(status_code=409, content={"error": "domain_error", "detail": str(exc)})

    @app.exception_handler(ValueError)
    async def _on_value(request: Request, exc: ValueError) -> JSONResponse:
        return JSONResponse(status_code=400, content={"error": "bad_request", "detail": str(exc)})

    # 频控超限（安全加固 A-4）→ 429
    @app.exception_handler(RateLimited)
    async def _on_rate_limited(request: Request, exc: RateLimited) -> JSONResponse:
        return JSONResponse(status_code=429, content={"error": "rate_limited", "detail": str(exc)})

    @app.exception_handler(KeyError)
    async def _on_key(request: Request, exc: KeyError) -> JSONResponse:
        return JSONResponse(status_code=400, content={"error": "not_supported", "detail": str(exc)})
