"""ISSUE-0030 失败落库验证（bogus-GPT 真实失败，零成本，无 mock）。

打 bogus-GPT 后端(:8003，GPT 指关闭端口) → listing 出图真实失败 → 应写 listing_job status=失败、0 成本、含 error。
cd image-code && uv run python ../image-qa/listing_history_fail_e2e.py
"""

import asyncio
import io
import json

import httpx

from qa_auth import login_verified_account
from PIL import Image

BASE = "http://127.0.0.1:8003"
SRC = "/Users/Zhuanz/CLAUDE/image-gen/花生/精修/02aa39d62d25800d3ee14fa91ab42242.jpg"


def png() -> bytes:
    b = io.BytesIO()
    Image.new("RGB", (768, 768), (230, 200, 150)).save(b, format="PNG")
    return b.getvalue()


async def main() -> None:
    async with httpx.AsyncClient(base_url=BASE, trust_env=False, timeout=120.0) as c:
        session = await login_verified_account(c)
        jwt = session.jwt
        H = {"Authorization": f"Bearer {jwt}"}
        uid = (await c.post("/uploads", headers=H, files={"file": ("p.png", png(), "image/png")})).json()["id"]
        body = {"upload_ids": [uid], "prompt": "失败用例", "ratio": "1:1", "n": 1, "modifiers": {"platform": "亚马逊"}}
        job = (await c.post("/listing/generate", headers=H, json=body)).json()["job_id"]
        print(f"[fail] job_id={job}；等真实失败(bogus GPT 连接失败+重试)…")
        evs = []
        async with c.stream("GET", f"/listing/{job}/events", params={"access_token": jwt}) as s:
            async for line in s.aiter_lines():
                if line.startswith("event:"):
                    et = line.split(":", 1)[1].strip()
                    evs.append(et)
                    if et in ("task_completed", "task_failed"):
                        break
        print(f"[fail] events={evs}")
        print(json.dumps({"job": job, "failed": "task_failed" in evs}))


asyncio.run(main())
