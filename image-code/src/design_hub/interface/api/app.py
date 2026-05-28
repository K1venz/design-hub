from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from design_hub.composition import Engine, build_engine
from design_hub.domain.errors import BudgetExceeded
from design_hub.interface.api.routes import generation
from design_hub.ports.model_provider import ProviderError


def register_error_handlers(app: FastAPI) -> None:
    """领域/端口错误在边界统一映射为 HTTP（翻译，非吞错）。"""

    @app.exception_handler(BudgetExceeded)
    async def _on_budget(request: Request, exc: BudgetExceeded) -> JSONResponse:
        return JSONResponse(
            status_code=409, content={"error": "budget_exceeded", "detail": exc.reason}
        )

    @app.exception_handler(ProviderError)
    async def _on_provider(request: Request, exc: ProviderError) -> JSONResponse:
        return JSONResponse(
            status_code=502, content={"error": "provider_failed", "detail": str(exc)}
        )

    @app.exception_handler(ValueError)
    async def _on_value(request: Request, exc: ValueError) -> JSONResponse:
        return JSONResponse(status_code=400, content={"error": "bad_request", "detail": str(exc)})

    @app.exception_handler(KeyError)
    async def _on_key(request: Request, exc: KeyError) -> JSONResponse:
        return JSONResponse(status_code=400, content={"error": "not_supported", "detail": str(exc)})


def create_app(engine: Engine | None = None) -> FastAPI:
    """同步应用工厂：默认全 Mock 引擎（零基础设施）；可注入替换引擎（DIP）。"""
    app = FastAPI(title="设计中台 · 图生图引擎", version="0.1.0")
    app.state.engine = engine if engine is not None else build_engine()
    app.include_router(generation.router)
    register_error_handlers(app)
    return app


app = create_app()
