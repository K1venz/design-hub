"""爆款复刻效果 demo（coordinator #812，给用户看效果、非回归）。

产品=通用块-花生.png（嘴嘴熊·高山七彩花生袋）；参考=共评样张/淘宝天猫1688-3x4-中文.png
（同款花生的真·爆款精修大图：大字标题+卖点角标+散落带壳花生+花生碗，零跨产品泄漏+最强爆款感）。
两档各 n=1：参考风格 + 高度复刻；ratio=3:4 配竖版爆款大图。SSE 断连降级轮询到终态。
成品落 image-qa/复刻demo/、打印绝对路径 + job 状态/cost。
用法：QA_BASE=http://localhost:8444 uv run python ../image-qa/clone_demo.py
"""

import asyncio
import io
import os
import time
from decimal import Decimal
from pathlib import Path

import httpx
from PIL import Image

BASE = (os.environ.get("QA_BASE") or os.environ.get("PROD_BASE") or "").rstrip("/")
PREFIX = os.environ.get("API_PREFIX", "").rstrip("/")
OUT = Path("/Users/Zhuanz/CLAUDE/image-gen/image-qa/复刻demo")
U = (f"qa-clonedemo-{int(time.time())}@example.com", "qa-clonedemo-123", "QA复刻demo")
PRODUCT = "/Users/Zhuanz/CLAUDE/image-gen/image-qa/通用块多产品/通用块-花生.png"
REFERENCE = "/Users/Zhuanz/CLAUDE/image-gen/image-qa/共评样张/淘宝天猫1688-3x4-中文.png"
MODS = {"platform": "淘宝天猫1688", "region": "中国", "language": "中文"}
MODES = ["参考风格", "高度复刻"]


def to_png(path: str) -> bytes:
    img = Image.open(path).convert("RGB")
    s = max(img.size)
    cv = Image.new("RGB", (s, s), (255, 255, 255))
    cv.paste(img, ((s - img.width) // 2, (s - img.height) // 2))
    b = io.BytesIO()
    cv.resize((1024, 1024)).save(b, format="PNG")
    return b.getvalue()


async def upload(c, H, path):  # noqa: ANN001
    return (await c.post(f"{PREFIX}/uploads", headers=H, files={"file": ("p.png", to_png(path), "image/png")})).json()["id"]


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
    OUT.mkdir(exist_ok=True)
    print(f"== 爆款复刻效果 demo == BASE={BASE}{PREFIX or ''}")
    print(f"   产品={Path(PRODUCT).name}  参考={Path(REFERENCE).name}（同款花生·爆款大图）  ratio=3:4")
    results = []
    async with httpx.AsyncClient(base_url=BASE, trust_env=False, verify=False, timeout=900.0) as c:
        r = await c.post(f"{PREFIX}/auth/register", json={"email": U[0], "password": U[1], "name": U[2]})
        if r.status_code != 200:
            r = await c.post(f"{PREFIX}/auth/login", json={"email": U[0], "password": U[1]})
        tok = r.json()["jwt"]
        H = {"Authorization": f"Bearer {tok}"}
        pid = await upload(c, H, PRODUCT)
        rid = await upload(c, H, REFERENCE)

        for mode in MODES:
            body = {"product_upload_ids": [pid], "reference_upload_ids": [rid], "clone_mode": mode,
                    "prompt": "电商主图：产品主体清晰、质感真实突出", "ratio": "3:4",
                    "category": "FOOD", "modifiers": MODS}
            t0 = time.perf_counter()
            job = (await c.post(f"{PREFIX}/listing/clone", headers=H, json=body)).json()["job_id"]
            d = await wait_job(c, H, tok, job)
            dt = int(time.perf_counter() - t0)
            imgs = [i for i in d.get("images", []) if i.get("status") == "成功"]
            tot = Decimal(str(d.get("total_cost", "0")))
            path = ""
            if imgs:
                async with httpx.AsyncClient(trust_env=False, verify=False, timeout=60.0) as dl:
                    resp = await dl.get(imgs[0]["url"])
                    if resp.status_code == 200:
                        path = str(OUT / f"复刻-{mode}.png")
                        Path(path).write_bytes(resp.content)
            results.append((mode, job, dt, d.get("status"), tot, d.get("clone_mode"), path))
            print(f"\n[{mode}] job={job} {dt}s status={d.get('status')} cost={tot} clone_mode回显={d.get('clone_mode')}")
            print(f"   成品 → {path or '（无：出图失败）'}")

    print("\n==== 复刻 demo 汇总（贴给 coordinator）====")
    for mode, job, dt, st, tot, cm, path in results:
        print(f"  · {mode}: {st} / cost={tot} / {dt}s / {path}")


asyncio.run(main())
