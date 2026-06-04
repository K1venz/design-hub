"""listing 真实出图 e2e（受控，真花钱）：走 /listing/generate(multipart) + SSE 取真实图。

用花生产品图 + modifiers(平台/地区/语言) + ratio + 自由 prompt → gpt-image-2 图生图。
cd image-code && uv run python ../image-qa/listing_real_e2e.py
"""

import asyncio
import io
import json
import time

import httpx
from PIL import Image

BASE = "http://127.0.0.1:8002"
SRC = "/Users/Zhuanz/CLAUDE/image-gen/花生/精修/02aa39d62d25800d3ee14fa91ab42242.jpg"
DESIGNER = ("qa-designer@test.com", "qa-designer-12345")


def to_png(path: str, side: int = 1024) -> bytes:
    img = Image.open(path).convert("RGB")
    s = max(img.size)
    canvas = Image.new("RGB", (s, s), (255, 255, 255))
    canvas.paste(img, ((s - img.width) // 2, (s - img.height) // 2))
    buf = io.BytesIO()
    canvas.resize((side, side)).save(buf, format="PNG")
    return buf.getvalue()


async def main() -> None:
    async with httpx.AsyncClient(base_url=BASE, trust_env=False, timeout=600.0) as c:
        r = await c.post("/auth/register", json={"email": DESIGNER[0], "password": DESIGNER[1], "name": "QA设计师"})
        if r.status_code != 200:
            r = await c.post("/auth/login", json={"email": DESIGNER[0], "password": DESIGNER[1]})
        jwt = r.json()["jwt"]
        H = {"Authorization": f"Bearer {jwt}", "X-User-Id": "qa-designer-001"}

        modifiers = {"platform": "亚马逊", "region": "美国", "language": "英文"}
        data = {
            "prompt": "突出高山七彩花生的天然颗粒与喜庆年货氛围，干净商业电商主图，主体清晰、包装文字清晰可读",
            "ratio": "3:4", "n": "1", "modifiers": json.dumps(modifiers, ensure_ascii=False),
        }
        files = [("images", ("peanut.png", to_png(SRC), "image/png"))]
        print(f"[POST] /listing/generate ratio=3:4 n=1 modifiers={modifiers}")
        r = await c.post("/listing/generate", headers=H, data=data, files=files)
        print(f"[POST] HTTP {r.status_code} {r.text[:200]}")
        if r.status_code != 200:
            return
        job_id = r.json()["job_id"]
        print(f"[POST] job_id={job_id}；订阅 SSE 等真实出图（edit 慢，~2-4 分钟）…")

        urls: list[str] = []
        cur_event: str | None = None
        t0 = time.perf_counter()
        async with c.stream("GET", f"/listing/{job_id}/events", params={"access_token": jwt}) as s:
            async for line in s.aiter_lines():
                if line.startswith("event:"):
                    etype = line.split(":", 1)[1].strip()
                    cur_event = etype
                elif line.startswith("data:") and cur_event:
                    payload = line.split(":", 1)[1].strip()
                    print(f"  [SSE {int(time.perf_counter()-t0)}s] {cur_event} {payload[:120]}")
                    if cur_event == "image_generated":
                        try:
                            urls.append(json.loads(payload)["url"])
                        except Exception:  # noqa: BLE001
                            pass
                    if cur_event in ("task_completed", "task_failed"):
                        break
        print(f"\n[RESULT] 出图 url(s): {urls}")


asyncio.run(main())
