"""ISSUE-0007 half-① re-verify (ZERO real cost): EDIT must fail-fast, not silently degrade to mock.

Against bogus-GPT :8001 (GPT base_url -> closed port): an EDIT request (with asset) routes to the
LIVE gpt provider which fails on connect; require_live_for_edit=True must REFUSE to fall back to the
mock seedream and instead raise -> HTTP 502 provider_failed + ledger rollback (no fake mock success).
The bogus connection failure stands in for the real 180s timeout; no real gpt-image call is made.
"""

import asyncio
import io

import httpx
from PIL import Image

BOGUS = "http://127.0.0.1:8001"


def png() -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", (512, 512), (200, 170, 110)).save(buf, format="PNG")
    return buf.getvalue()


async def main() -> None:
    async with httpx.AsyncClient(base_url=BOGUS, trust_env=False, timeout=120.0) as c:
        jwt = (await c.post("/auth/feishu/callback", json={"code": "designer-ff"})).json()["jwt"]
        h = {"Authorization": f"Bearer {jwt}"}
        gh = {**h, "X-User-Id": "failfast-001"}

        cid = (await c.post("/customers", headers=h, json={"name": "QA-failfast"})).json()["id"]
        pid = (await c.post("/projects", headers=h, json={"customer_id": cid, "name": "ff项目"})).json()["id"]
        aid = (await c.post(f"/projects/{pid}/assets", headers=h, data={"kind": "产品图"},
                            files={"file": ("p.png", png(), "image/png")})).json()["id"]
        print(f"[0007半①] customer={cid} project={pid} asset={aid}")

        body = {"subscene": "S1", "family": "family_4", "category": "食品", "tier": "standard",
                "style": "清新自然", "width": 512, "height": 512, "n": 1, "asset_ids": [aid]}  # 有素材 -> EDIT
        r = await c.post(f"/projects/{pid}/generate", headers=gh, json=body)
        print(f"[0007半①] EDIT 出图 -> HTTP {r.status_code} body={r.text[:200]}")

        is_502 = r.status_code == 502
        no_mock = "mock://" not in r.text  # 必须没有 mock 假成功
        print(f"[0007半①] RESULT = {'PASS' if (is_502 and no_mock) else 'FAIL'} "
              f"(期望 502 provider_failed 且不返回 mock 假成功；fail-fast 生效)")


asyncio.run(main())
