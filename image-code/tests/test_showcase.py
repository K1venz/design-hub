"""公开 GET /showcase（首页成果展示区）：无鉴权、清单驱动、现签 url、空清单 []。"""

import pytest
from fastapi import FastAPI
from fastapi.routing import APIRoute
from fastapi.testclient import TestClient

from design_hub.config.showcase import SHOWCASE_ENTRIES, ShowcaseEntry
from design_hub.interface.api.asgi import create_production_app
from design_hub.interface.api.deps import get_current_user, get_current_user_sse
from design_hub.interface.api.routes import showcase
from design_hub.ports.media_url_signer import MediaUrlSigner


class _StubSigner(MediaUrlSigner):
    def generated_url(self, key: str) -> str:
        return f"https://signed.example/{key}?sig=x"

    def upload_url(self, key: str) -> str:
        raise AssertionError("showcase 只签 generate 桶，不该触上传桶")


def _client() -> TestClient:
    app = FastAPI()
    app.include_router(showcase.router)
    app.state.media_signer = _StubSigner()
    return TestClient(app)


def test_showcase_200_shape_without_auth(monkeypatch: pytest.MonkeyPatch) -> None:
    entries = (
        ShowcaseEntry(key="showcase/01.png", image_type="白底", caption="花生·白底主图"),
        ShowcaseEntry(key="showcase/02.png", image_type="场景", caption="花生·场景图"),
    )
    monkeypatch.setattr(showcase, "SHOWCASE_ENTRIES", entries)
    resp = _client().get("/showcase")  # 不带 Authorization 头（公开访客视角）
    assert resp.status_code == 200
    assert resp.json() == [
        {
            "url": "https://signed.example/showcase/01.png?sig=x",
            "image_type": "白底",
            "caption": "花生·白底主图",
        },
        {
            "url": "https://signed.example/showcase/02.png?sig=x",
            "image_type": "场景",
            "caption": "花生·场景图",
        },
    ]


def test_showcase_empty_manifest_returns_empty_list(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(showcase, "SHOWCASE_ENTRIES", ())
    resp = _client().get("/showcase")
    assert resp.status_code == 200
    assert resp.json() == []


def _dep_calls(dependant):  # type: ignore[no-untyped-def]
    for dep in dependant.dependencies:
        yield dep.call
        yield from _dep_calls(dep)


def test_showcase_route_mounted_public_in_production_app() -> None:
    app = create_production_app()
    route = next(
        r for r in app.routes if isinstance(r, APIRoute) and r.path == "/showcase"
    )
    calls = set(_dep_calls(route.dependant))
    assert get_current_user not in calls
    assert get_current_user_sse not in calls


def test_curated_manifest_invariants() -> None:
    # 入库清单卫兵：key 前缀/唯一、图型枚举、说明非空（改清单时 fail-fast）。
    keys = [e.key for e in SHOWCASE_ENTRIES]
    assert len(keys) == len(set(keys))
    for e in SHOWCASE_ENTRIES:
        assert e.key.startswith("showcase/")
        assert e.image_type in {"白底", "场景", "卖点"}
        assert e.caption.strip()
