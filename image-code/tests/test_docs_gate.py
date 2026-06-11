"""app 层 docs 开关（安全加固 A-2 纵深：按 env 从源头摘除文档路由）。"""

import pytest
from fastapi import FastAPI

from design_hub.config.settings import Settings
from design_hub.interface.api.asgi import create_production_app

_DOC_PATHS = {"/docs", "/redoc", "/openapi.json"}


def _route_paths(app: FastAPI) -> set[str]:
    return {route.path for route in app.routes}


def test_docs_disabled_is_code_default(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("DOCS_ENABLED", raising=False)
    # 不读 env 文件：纯代码默认=关（prod 不配即闭，忘配=安全）
    assert Settings(_env_file=None).docs_enabled is False


def test_docs_routes_absent_when_disabled(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DOCS_ENABLED", "false")
    assert not _DOC_PATHS & _route_paths(create_production_app())


def test_docs_routes_present_when_enabled(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DOCS_ENABLED", "true")
    assert _DOC_PATHS <= _route_paths(create_production_app())
