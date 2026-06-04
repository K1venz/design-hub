"""ISSUE-0023 Layer2 HTTP/SSE：httpx ASGITransport in-process + Mock provider（无 DB，token 直 mint）。

覆盖：入参/边界、401、SSE 全序列/task_failed/晚订阅回放。
cd image-code && uv run python ../image-qa/listing_test_http.py
"""

import asyncio
import json
from decimal import Decimal

import httpx
from fastapi import FastAPI

from design_hub.application.cost.budget import BudgetPolicy
from design_hub.application.cost.guard import CostGuard
from design_hub.application.listing.listing_service import ListingGenerationService
from design_hub.application.listing.prompt_composer import PromptModifierRegistry
from design_hub.application.registry import ProviderRegistry
from design_hub.domain.enums import ModelName, Role
from design_hub.domain.models import AuthUser
from design_hub.infrastructure.auth.jwt_service import PyJwtTokenService
from design_hub.infrastructure.events.memory import InMemoryEventBus
from design_hub.infrastructure.ledger.memory import InMemoryLedgerRepository
from design_hub.infrastructure.listing.noop_history import NoOpListingHistory
from design_hub.infrastructure.providers.mock import MockModelProvider
from design_hub.infrastructure.queue.in_process import InProcessTaskQueue
from design_hub.interface.api.app import register_error_handlers
from design_hub.interface.api.routes import listing

R: list[tuple[str, bool]] = []


def check(name: str, cond: bool, detail: str = "") -> None:
    R.append((name, bool(cond)))
    print(f"[{'PASS' if cond else 'FAIL'}] {name} {detail}")


def build_app(fail: bool = False) -> tuple[FastAPI, str]:
    app = FastAPI()
    reg = ProviderRegistry()
    reg.register(MockModelProvider(name=ModelName.GPT_IMAGE_2, unit_cost=Decimal("1.19"), fail=fail))
    ts = PyJwtTokenService(secret="qa-test-secret-min-32-bytes-aaaaaaaa", ttl_hours=24)
    app.state.token_service = ts
    app.state.listing_service = ListingGenerationService(
        registry=reg, guard=CostGuard(ledger=InMemoryLedgerRepository(), policy=BudgetPolicy()),
        modifier_registry=PromptModifierRegistry(),
    )
    app.state.task_queue = InProcessTaskQueue()
    app.state.event_stream = InMemoryEventBus()
    app.state.listing_history = NoOpListingHistory()
    app.include_router(listing.router)
    register_error_handlers(app)
    token = ts.issue(AuthUser(user_id="u1", name="QA", role=Role.DESIGNER, dept=None))
    return app, token


IMG = ("a.png", b"\x89PNG\r\n\x1a\n", "image/png")


def files(k: int) -> list[tuple[str, tuple[str, bytes, str]]]:
    return [("images", IMG) for _ in range(k)]


def form(prompt: str = "纯白背景突出产品", ratio: str = "1:1", n: int = 2, modifiers: dict | None = None) -> dict:
    return {"prompt": prompt, "ratio": ratio, "n": str(n),
            "modifiers": json.dumps(modifiers if modifiers is not None else {"platform": "亚马逊"})}


async def collect_sse(c: httpx.AsyncClient, job_id: str, token: str, delay: float = 0.0) -> list[str]:
    if delay:
        await asyncio.sleep(delay)
    evs: list[str] = []

    async def _run() -> None:
        async with c.stream("GET", f"/listing/{job_id}/events", params={"access_token": token}) as s:
            async for line in s.aiter_lines():
                if line.startswith("event:"):
                    et = line.split(":", 1)[1].strip()
                    evs.append(et)
                    if et in ("task_completed", "task_failed"):
                        return

    try:
        await asyncio.wait_for(_run(), timeout=15.0)
    except TimeoutError:
        evs.append("<timeout>")
    return evs


async def main() -> None:
    app, token = build_app()
    H = {"Authorization": f"Bearer {token}"}
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://t", timeout=20.0) as c:
        # 用例1：1/2/3 图 + 合法 modifiers → 200 + job_id
        for k in (1, 2, 3):
            r = await c.post("/listing/generate", headers=H, files=files(k), data=form(n=2))
            check(f"1.{k}图合法→200+job_id", r.status_code == 200 and "job_id" in r.json(), f"HTTP {r.status_code}")
        # 用例2：0 / >3 图 → 4xx
        r = await c.post("/listing/generate", headers=H, files=files(4), data=form())
        check("2.>3图→4xx", 400 <= r.status_code < 500, f"HTTP {r.status_code} {r.text[:60]}")
        r = await c.post("/listing/generate", headers=H, data=form())  # 无 images 字段
        check("2.0图→4xx", 400 <= r.status_code < 500, f"HTTP {r.status_code}")
        # 用例4：modifiers 非法 JSON / 非对象 → 4xx
        r = await c.post("/listing/generate", headers=H, files=files(1), data={**form(), "modifiers": "{坏"})
        check("4.非法JSON modifiers→400", r.status_code == 400, f"HTTP {r.status_code}")
        r = await c.post("/listing/generate", headers=H, files=files(1), data={**form(), "modifiers": "[1,2]"})
        check("4.非对象 modifiers→4xx", 400 <= r.status_code < 500, f"HTTP {r.status_code}")
        # 用例7：鉴权
        r = await c.post("/listing/generate", files=files(1), data=form())
        check("7.无Bearer→401", r.status_code == 401, f"HTTP {r.status_code}")
        r = await c.get("/listing/none/events")
        check("7.SSE无access_token→401", r.status_code == 401, f"HTTP {r.status_code}")

        # 用例3/5/6：边界应 fail-fast 4xx（spec §4.1/§7）——实测当前实现
        r = await c.post("/listing/generate", headers=H, files=files(1), data=form(n=8))
        check("3.n=8 HTTP边界→应4xx", 400 <= r.status_code < 500, f"HTTP {r.status_code}（200=边界未fail-fast bug）")
        r = await c.post("/listing/generate", headers=H, files=files(1), data=form(ratio="2:1"))
        check("6.非法ratio HTTP边界→应4xx", 400 <= r.status_code < 500, f"HTTP {r.status_code}（200=边界未fail-fast bug）")
        r = await c.post("/listing/generate", headers=H, files=files(1), data=form(modifiers={"platform": "未知平台"}))
        check("5.未知下拉 HTTP边界→应4xx", 400 <= r.status_code < 500, f"HTTP {r.status_code}（200=边界未fail-fast bug）")
        r = await c.post("/listing/generate", headers=H, files=files(1), data=form(prompt="   "))
        check("附.空prompt HTTP边界→应4xx", 400 <= r.status_code < 500, f"HTTP {r.status_code}（200=边界未fail-fast bug）")

        # 用例8：SSE 全序列（合法 n=3）
        r = await c.post("/listing/generate", headers=H, files=files(1), data=form(n=3))
        jid = r.json()["job_id"]
        evs = await collect_sse(c, jid, token)
        seq_ok = evs[:2] == ["task_started", "model_called"] and evs.count("image_generated") == 3 and evs[-1] == "task_completed"
        check("8.SSE全序列 started→model→image×3→completed", seq_ok, f"{evs}")

        # 用例10：晚订阅回放（延迟 0.6s 再订阅，仍收齐）
        r = await c.post("/listing/generate", headers=H, files=files(1), data=form(n=2))
        jid = r.json()["job_id"]
        evs = await collect_sse(c, jid, token, delay=0.6)
        check("10.晚订阅回放全序列", "task_started" in evs and "task_completed" in evs, f"{evs}")

    # 用例9：provider 真失败 → task_failed（独立 fail=True app，请求合法）
    app_f, token_f = build_app(fail=True)
    Hf = {"Authorization": f"Bearer {token_f}"}
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app_f), base_url="http://t", timeout=20.0) as cf:
        r = await cf.post("/listing/generate", headers=Hf, files=files(1), data=form(n=2))
        jid = r.json()["job_id"]
        evs = await collect_sse(cf, jid, token_f)
        check("9.provider失败→task_failed(不静默吞)", "task_failed" in evs and "task_completed" not in evs, f"{evs}")

    n = sum(1 for _, c in R if c)
    print(f"\n==== HTTP/SSE: {n}/{len(R)} passed ====")


asyncio.run(main())
