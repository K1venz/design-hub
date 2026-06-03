"""花生 project 1 多风格候选补出图（真实图生图 EDIT，3 张并发）。

同一张产品图(嘴嘴熊高山七彩花生) + 3 种已注册风格(高端轻奢/国潮中式/极简北欧)，
挂 project 1 第一轮，凑齐候选给用户挑。真实 gpt-image-2 /images/edits，各 ~¥1.19。
"""

import asyncio
import io
import json
import time

import httpx
from PIL import Image

BASE = "http://127.0.0.1:8000"
SRC = "/Users/Zhuanz/CLAUDE/image-gen/花生/精修/02aa39d62d25800d3ee14fa91ab42242.jpg"
DESIGNER = ("qa-designer@test.com", "qa-designer-12345")
PROJECT = 1
STYLES = ["高端轻奢", "国潮中式", "极简北欧"]
OUT = "/tmp/peanut-more-result.json"


def to_square_png(path: str, side: int = 1024) -> bytes:
    img = Image.open(path).convert("RGB")
    s = max(img.size)
    canvas = Image.new("RGB", (s, s), (255, 255, 255))
    canvas.paste(img, ((s - img.width) // 2, (s - img.height) // 2))
    return _png(canvas.resize((side, side)))


def _png(img: Image.Image) -> bytes:
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


async def gen_one(c: httpx.AsyncClient, gh: dict, aid: int, style: str) -> dict:
    body = {"subscene": "S1", "family": "family_4", "category": "食品", "tier": "standard",
            "style": style, "width": 1024, "height": 1024, "n": 1, "asset_ids": [aid]}
    t0 = time.perf_counter()
    try:
        r = await c.post(f"/projects/{PROJECT}/generate", headers=gh, json=body)
        dt = int((time.perf_counter() - t0) * 1000)
        if r.status_code != 200:
            return {"style": style, "ok": False, "http": r.status_code, "detail": r.text[:160], "ms": dt}
        j = r.json()
        url = (j.get("images") or [{}])[0].get("url", "")
        return {"style": style, "ok": j["used_model"] == "gpt-image-2", "http": 200,
                "used_model": j["used_model"], "job_id": j["job_id"], "url": url,
                "cost": j["total_cost"], "ms": dt}
    except Exception as exc:  # noqa: BLE001
        return {"style": style, "ok": False, "detail": f"{type(exc).__name__}: {exc}",
                "ms": int((time.perf_counter() - t0) * 1000)}


async def main() -> None:
    async with httpx.AsyncClient(base_url=BASE, trust_env=False, timeout=600.0) as c:
        r = await c.post("/auth/login", json={"email": DESIGNER[0], "password": DESIGNER[1]})
        jwt = r.json()["jwt"]
        h = {"Authorization": f"Bearer {jwt}"}
        gh = {**h, "X-User-Id": "qa-designer-001"}

        png = to_square_png(SRC)
        aid = (await c.post(f"/projects/{PROJECT}/assets", headers=h, data={"kind": "产品图"},
                            files={"file": ("peanut.png", png, "image/png")})).json()["id"]
        print(f"[setup] project={PROJECT} asset={aid}；并发出 {len(STYLES)} 张：{STYLES}")

        results = await asyncio.gather(*[gen_one(c, gh, aid, s) for s in STYLES])
        for r in results:
            tag = "PASS" if r.get("ok") else "FAIL"
            print(f"[{tag}] 风格={r['style']} :: {json.dumps(r, ensure_ascii=False)}")
        with open(OUT, "w") as f:
            json.dump(results, f, ensure_ascii=False, indent=2)
        ok = sum(1 for r in results if r.get("ok"))
        print(f"\n==== {ok}/{len(STYLES)} 张真实花生出图成功 → project {PROJECT} 第1轮 ====")
        print(f"结果(含图路径) -> {OUT}")


asyncio.run(main())
