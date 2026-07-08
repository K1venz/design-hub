"""公开 GET /showcase（首页成果展示区）：无鉴权、清单驱动、现签 url、空清单 []。"""

import pytest
from fastapi import FastAPI
from fastapi.routing import APIRoute
from fastapi.testclient import TestClient

from design_hub.config.showcase import SHOWCASE_ENTRIES, Recipe, ShowcaseEntry
from design_hub.interface.api.asgi import create_production_app
from design_hub.interface.api.deps import get_current_user, get_current_user_sse
from design_hub.interface.api.routes import showcase
from design_hub.ports.media_url_signer import MediaUrlSigner

_FIXTURE_RECIPE = Recipe(
    category="FOOD",
    ratio="1:1",
    plan={"白底": 1, "场景": 2, "卖点": 2},
    styling="暖调原木餐桌，柔和自然晨光，画面干净高级",
    modifiers={"region": "中国", "language": "中文", "platform": "淘宝天猫1688"},
)
_FIXTURE_RECIPE_JSON = {
    "category": "FOOD",
    "ratio": "1:1",
    "plan": {"白底": 1, "场景": 2, "卖点": 2},
    "styling": "暖调原木餐桌，柔和自然晨光，画面干净高级",
    "modifiers": {"region": "中国", "language": "中文", "platform": "淘宝天猫1688"},
}


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
        ShowcaseEntry("showcase/01.png", "白底", "花生·白底主图", _FIXTURE_RECIPE),
        ShowcaseEntry("showcase/02.png", "场景", "花生·场景图", _FIXTURE_RECIPE),
    )
    monkeypatch.setattr(showcase, "SHOWCASE_ENTRIES", entries)
    resp = _client().get("/showcase")  # 不带 Authorization 头（公开访客视角）
    assert resp.status_code == 200
    assert resp.json() == [
        {
            "url": "https://signed.example/showcase/01.png?sig=x",
            "image_type": "白底",
            "caption": "花生·白底主图",
            "recipe": _FIXTURE_RECIPE_JSON,
        },
        {
            "url": "https://signed.example/showcase/02.png?sig=x",
            "image_type": "场景",
            "caption": "花生·场景图",
            "recipe": _FIXTURE_RECIPE_JSON,
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


# 内部卡 prompt 泄漏哨兵（ISSUE-0053 验收③铁律）：配方 styling=用户自由文本，
# 绝不能混入卡体系组装标记。命中即说明有人把组装后 prompt 误灌进配方。
_CARD_LEAK_MARKERS = ("图型·", "保真", "版式参考", "按这种风格", "真实商业摄影质感", "影棚")


def test_recipe_reuse_invariants() -> None:
    # 配方卫兵（做同款可复用性 + 无内部 prompt 泄漏）：改配方时 fail-fast。
    for e in SHOWCASE_ENTRIES:
        r = e.recipe
        # 品类 ∈ 五品类枚举（ISSUE-0060 扩展后 showcase 含 FASHION/SHOES/DIGITAL 精选）
        assert r.category in {"FOOD", "FASHION", "BEAUTY", "SHOES", "DIGITAL"}
        assert r.ratio in {"1:1", "9:16", "16:9", "3:4", "4:3"}
        # 图型配比：键为图型枚举、张数为正、Σ 在套图区间 3..10（PRD §3.12.14）
        assert set(r.plan).issubset({"白底", "场景", "卖点"})
        assert all(v > 0 for v in r.plan.values())
        assert 3 <= sum(r.plan.values()) <= 10
        # 本项图型必在所属套图配比内（回显/复用一致）
        assert e.image_type in r.plan
        # modifiers 携带可复用平台/语言（做同款预填必需，缺则前端建不出请求）
        assert r.modifiers.get("platform", "").strip()
        assert r.modifiers.get("language", "").strip()
        # 风格描述非空、且不泄漏内部卡组装标记（验收③）
        assert r.styling.strip()
        for marker in _CARD_LEAK_MARKERS:
            assert marker not in r.styling
