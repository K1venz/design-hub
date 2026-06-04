"""listing 两步流真实 e2e（受控，真花钱，n=1）：POST /uploads → /listing/generate(upload_ids) → SSE。

C: 单图两步流复跑（ISSUE-0026 契约）。
D: 多图(2 张) upload_ids → 看上游真实 edit 是否支持多图（ISSUE-0025 残留①）。
cd image-code && uv run python ../image-qa/listing_real_e2e.py
"""

import asyncio
import io
import json
import time

import httpx
from PIL import Image

BASE = "http://127.0.0.1:8002"
SRC1 = "/Users/Zhuanz/CLAUDE/image-gen/花生/精修/02aa39d62d25800d3ee14fa91ab42242.jpg"
SRC2 = "/Users/Zhuanz/CLAUDE/image-gen/花生/精修/2c89de896fc69ea4b7b4bca32f26be91.jpg"
DESIGNER = ("qa-designer@test.com", "qa-designer-12345")


def to_png(path: str, side: int = 1024) -> bytes:
    img = Image.open(path).convert("RGB")
    s = max(img.size)
    canvas = Image.new("RGB", (s, s), (255, 255, 255))
    canvas.paste(img, ((s - img.width) // 2, (s - img.height) // 2))
    buf = io.BytesIO()
    canvas.resize((side, side)).save(buf, format="PNG")
    return buf.getvalue()


async def sse(c: httpx.AsyncClient, jwt: str, job_id: str) -> tuple[list[str], list[str]]:
    events: list[str] = []
    urls: list[str] = []
    cur: str | None = None
    t0 = time.perf_counter()
    async with c.stream("GET", f"/listing/{job_id}/events", params={"access_token": jwt}) as s:
        async for line in s.aiter_lines():
            if line.startswith("event:"):
                cur = line.split(":", 1)[1].strip()
                events.append(cur)
            elif line.startswith("data:") and cur:
                payload = line.split(":", 1)[1].strip()
                print(f"  [{int(time.perf_counter()-t0)}s] {cur} {payload[:110]}")
                if cur == "image_generated":
                    try:
                        urls.append(json.loads(payload)["url"])
                    except Exception:  # noqa: BLE001
                        pass
                if cur in ("task_completed", "task_failed"):
                    break
    return events, urls


async def run_case(c: httpx.AsyncClient, jwt: str, H: dict, tag: str, upload_ids: list[str], ratio: str) -> None:
    body = {"upload_ids": upload_ids, "ratio": ratio, "n": 1,
            "prompt": "突出高山七彩花生的天然颗粒与喜庆年货氛围，干净商业电商主图，主体清晰、包装文字清晰可读",
            "modifiers": {"platform": "亚马逊", "region": "美国", "language": "英文"}}
    print(f"\n=== {tag}: upload_ids={upload_ids} ratio={ratio} n=1 ===")
    r = await c.post("/listing/generate", headers=H, json=body)
    print(f"[generate] HTTP {r.status_code} {r.text[:150]}")
    if r.status_code != 200:
        return
    job_id = r.json()["job_id"]
    events, urls = await sse(c, jwt, job_id)
    print(f"[{tag}] events={events}  urls={urls}")


async def main() -> None:
    async with httpx.AsyncClient(base_url=BASE, trust_env=False, timeout=600.0) as c:
        r = await c.post("/auth/register", json={"email": DESIGNER[0], "password": DESIGNER[1], "name": "QA设计师"})
        if r.status_code != 200:
            r = await c.post("/auth/login", json={"email": DESIGNER[0], "password": DESIGNER[1]})
        jwt = r.json()["jwt"]
        H = {"Authorization": f"Bearer {jwt}", "X-User-Id": "qa-designer-001"}

        async def upload(path: str) -> str:
            r = await c.post("/uploads", headers=H, files={"file": ("p.png", to_png(path), "image/png")})
            print(f"[upload] {path.split('/')[-1]} -> HTTP {r.status_code} {r.json() if r.status_code==200 else r.text[:80]}")
            return r.json()["id"]

        id1 = await upload(SRC1)
        # C: 单图两步流
        await run_case(c, jwt, H, "C 单图两步流", [id1], "3:4")
        # D: 双图（不同图 → 不同 id）
        id2 = await upload(SRC2)
        await run_case(c, jwt, H, "D 双图多图edit", [id1, id2], "1:1")


asyncio.run(main())
