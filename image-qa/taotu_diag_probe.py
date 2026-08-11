"""诊断探针：一张 n=1 真出图，抓 job 详情全文 + SSE 全事件，定位失败根因（零成本=失败不计费）。"""
import asyncio
import io
import json
import os

import httpx

from qa_auth import login_verified_account
from PIL import Image

BASE = os.environ.get("QA_BASE", "").rstrip("/")
SRC = "/Users/Zhuanz/CLAUDE/image-gen/image-qa/通用块多产品/通用块-花生.png"
def to_png(p):  # noqa: ANN001
    img = Image.open(p).convert("RGB")
    s = max(img.size)
    cv = Image.new("RGB", (s, s), (255, 255, 255))
    cv.paste(img, ((s - img.width) // 2, (s - img.height) // 2))
    b = io.BytesIO()
    cv.resize((1024, 1024)).save(b, format="PNG")
    return b.getvalue()


async def main():  # noqa: ANN001
    async with httpx.AsyncClient(base_url=BASE, trust_env=False, timeout=300.0) as c:
        session = await login_verified_account(c)
        tok = session.jwt
        H = {"Authorization": f"Bearer {tok}"}
        uid = (await c.post("/uploads", headers=H, files={"file": ("p.png", to_png(SRC), "image/png")})).json()["id"]
        body = {"upload_ids": [uid], "prompt": "电商主图：产品主体清晰", "ratio": "1:1", "n": 1,
                "category": "FOOD", "modifiers": {"platform": "淘宝天猫1688", "region": "中国", "language": "中文"}}
        job = (await c.post("/listing/generate", headers=H, json=body)).json()["job_id"]
        print(f"job={job}")
        async with c.stream("GET", f"/listing/{job}/events", params={"access_token": tok}) as s:
            ev = None
            async for line in s.aiter_lines():
                if line.startswith("event:"):
                    ev = line.split(":", 1)[1].strip()
                elif line.startswith("data:"):
                    print(f"  SSE [{ev}] {line.split(':', 1)[1].strip()[:300]}")
                    if ev in ("task_completed", "task_failed"):
                        break
        d = (await c.get(f"/listing/jobs/{job}", headers=H)).json()
        print("JOB DETAIL:", json.dumps(d, ensure_ascii=False)[:800])


asyncio.run(main())
