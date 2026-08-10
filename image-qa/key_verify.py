"""中转站 apikey 轮换验证 — 真出图（coordinator #815，ops recreate 后跑）。

验「新 key 能真出图」（不只 /v1/models 认证 200，而是走完整 generate → 中转站真返图）：
auth → upload → 单图流 n=1 → 断言 完成 + 1 张成功图 + cost>0 + 有 image url。
qa(QA_BASE) / prod(PROD_BASE+API_PREFIX=/api) 同源。¥0.40/发。
用法：
  qa：  QA_BASE=http://localhost:8444 uv run python ../image-qa/key_verify.py
  prod：PROD_BASE=https://203.0.113.10 API_PREFIX=/api uv run python ../image-qa/key_verify.py
"""

import asyncio
import io
import os
import time
from decimal import Decimal

import httpx

from qa_auth import login_verified_account
from PIL import Image

BASE = (os.environ.get("QA_BASE") or os.environ.get("PROD_BASE") or "").rstrip("/")
PREFIX = os.environ.get("API_PREFIX", "").rstrip("/")
SRC = "/Users/Zhuanz/CLAUDE/image-gen/image-qa/通用块多产品/通用块-花生.png"
MODS = {"platform": "淘宝天猫1688", "region": "中国", "language": "中文"}


def to_png(path: str) -> bytes:
    img = Image.open(path).convert("RGB")
    s = max(img.size)
    cv = Image.new("RGB", (s, s), (255, 255, 255))
    cv.paste(img, ((s - img.width) // 2, (s - img.height) // 2))
    b = io.BytesIO()
    cv.resize((1024, 1024)).save(b, format="PNG")
    return b.getvalue()


async def wait_job(c, H, tok, job):  # noqa: ANN001
    try:
        async with c.stream("GET", f"{PREFIX}/listing/{job}/events", params={"access_token": tok}) as s:
            ev = None
            async for line in s.aiter_lines():
                if line.startswith("event:"):
                    ev = line.split(":", 1)[1].strip()
                    if ev in ("task_completed", "task_failed"):
                        break
    except httpx.RemoteProtocolError:
        print(f"  [SSE 断连→降级轮询 job={job}]")
    for _ in range(200):
        d = (await c.get(f"{PREFIX}/listing/jobs/{job}", headers=H)).json()
        if d.get("status") in ("完成", "失败"):
            return d
        await asyncio.sleep(3)
    return (await c.get(f"{PREFIX}/listing/jobs/{job}", headers=H)).json()


async def main() -> None:
    if not BASE:
        raise SystemExit("✋ 未设 QA_BASE/PROD_BASE。")
    print(f"== 中转站新 key 真出图验证 == BASE={BASE}{PREFIX or ''}")
    async with httpx.AsyncClient(base_url=BASE, trust_env=False, verify=False, timeout=600.0) as c:
        session = await login_verified_account(c, prefix=PREFIX)
        tok = session.jwt
        H = {"Authorization": f"Bearer {tok}"}
        uid = (await c.post(f"{PREFIX}/uploads", headers=H, files={"file": ("p.png", to_png(SRC), "image/png")})).json()["id"]
        body = {"upload_ids": [uid], "prompt": "电商主图：产品主体清晰、质感真实突出",
                "ratio": "1:1", "n": 1, "category": "FOOD", "modifiers": MODS}
        t0 = time.perf_counter()
        job = (await c.post(f"{PREFIX}/listing/generate", headers=H, json=body)).json()["job_id"]
        d = await wait_job(c, H, tok, job)
        dt = int(time.perf_counter() - t0)
        imgs = [i for i in d.get("images", []) if i.get("status") == "成功"]
        tot = Decimal(str(d.get("total_cost", "0")))
        url = imgs[0].get("url") if imgs else ""
        ok = d.get("status") == "完成" and len(imgs) == 1 and tot > 0 and bool(url)
        print(f"\n  {'PASS' if ok else '🔴 FAIL'}  job={job} {dt}s status={d.get('status')} 成功图={len(imgs)} cost={tot}")
        print(f"  image url: {url or '（无：新 key 未真出图）'}")
        print(f"\n==== 新 key 真出图验证：{'绿（新 key 能真出图）' if ok else '🔴 红（STOP 报 coordinator、别硬切 prod）'} ====")
        if not ok:
            raise SystemExit(1)


asyncio.run(main())
