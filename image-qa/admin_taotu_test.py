"""用户指定:admin 账号 prod 测两次套图(花生 + 其他商品)。

登录 admin（creds 从 env、不硬编码不入库）→ 两次默认套图(白底1/场景2/卖点2=5)：
① 花生(通用块-花生.png) ② 润喉糖(套图回归/润喉糖-白底.png，其他商品·同 FOOD 品类)。
SSE 断连降级轮询。成品落 image-qa/admin套图test/、打印路径 + job/状态/cost。
用法：PROD_BASE=https://14.103.51.191 API_PREFIX=/api ADMIN_EMAIL=... ADMIN_PASSWORD=... \
      uv run python ../image-qa/admin_taotu_test.py
"""

import asyncio
import io
import os
import time
from decimal import Decimal
from pathlib import Path

import httpx

from qa_auth import AccountSlot, login_verified_account
from PIL import Image

BASE = (os.environ.get("PROD_BASE") or os.environ.get("QA_BASE") or "").rstrip("/")
PREFIX = os.environ.get("API_PREFIX", "").rstrip("/")
OUT = Path("/Users/Zhuanz/CLAUDE/image-gen/image-qa/admin套图test")
MODS = {"platform": "淘宝天猫1688", "region": "中国", "language": "中文"}
PLAN = {"白底": 1, "场景": 2, "卖点": 2}  # 默认套图 5 张
PRODUCTS = [
    ("花生", "/Users/Zhuanz/CLAUDE/image-gen/image-qa/通用块多产品/通用块-花生.png", ["高山七彩花生", "原生态种植"]),
    ("润喉糖", "/Users/Zhuanz/CLAUDE/image-gen/image-qa/套图回归/润喉糖-白底.png", ["草本润喉", "清甜不腻"]),
]


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
    for _ in range(240):
        d = (await c.get(f"{PREFIX}/listing/jobs/{job}", headers=H)).json()
        if d.get("status") in ("完成", "失败"):
            return d
        await asyncio.sleep(3)
    return (await c.get(f"{PREFIX}/listing/jobs/{job}", headers=H)).json()


async def dl(url, fname):  # noqa: ANN001
    async with httpx.AsyncClient(trust_env=False, verify=False, timeout=60.0) as d:
        r = await d.get(url)
        if r.status_code == 200:
            (OUT / fname).write_bytes(r.content)
            return str(OUT / fname)
    return ""


async def main() -> None:
    if not BASE:
        raise SystemExit("✋ 需 PROD_BASE/ADMIN_EMAIL/ADMIN_PASSWORD。")
    OUT.mkdir(exist_ok=True)
    print(f"== admin 套图实测 == BASE={BASE}{PREFIX or ''} 账号=runtime ADMIN_EMAIL")
    async with httpx.AsyncClient(base_url=BASE, trust_env=False, verify=False, timeout=900.0) as c:
        session = await login_verified_account(c, prefix=PREFIX, slot=AccountSlot.ADMIN)
        tok = session.jwt
        H = {"Authorization": f"Bearer {tok}"}
        print(f"  Login succeeded for {session.email}")

        summary = []
        for label, src, overlay in PRODUCTS:
            uid = (await c.post(f"{PREFIX}/uploads", headers=H, files={"file": ("p.png", to_png(src), "image/png")})).json()["id"]
            body = {"upload_ids": [uid], "prompt": "电商主图：产品主体清晰、背景干净得体、质感真实突出",
                    "ratio": "1:1", "category": "FOOD", "modifiers": MODS, "plan": PLAN, "overlay_texts": overlay}
            t0 = time.perf_counter()
            job = (await c.post(f"{PREFIX}/listing/generate", headers=H, json=body)).json()["job_id"]
            d = await wait_job(c, H, tok, job)
            dt = int(time.perf_counter() - t0)
            imgs = [i for i in d.get("images", []) if i.get("status") == "成功"]
            dist = sorted(i.get("image_type") or "?" for i in imgs)
            tot = Decimal(str(d.get("total_cost", "0")))
            print(f"\n[{label}] job={job} {dt}s status={d.get('status')} cost={tot} 成功={len(imgs)}/5 dist={dist}")
            paths = []
            for i in imgs:
                t = i.get("image_type")
                p = await dl(i["url"], f"{label}-{t}-{i['url'].split('/')[-1][:8]}.png")
                if p:
                    paths.append(p)
            for p in paths:
                print(f"   {p}")
            summary.append((label, job, d.get("status"), len(imgs), tot, dist, paths))

    print("\n==== admin 套图实测汇总 ====")
    for label, job, st, n, tot, dist, paths in summary:
        print(f"  · {label}: {st} / {n}张 {dist} / cost=¥{tot} / job={job}")
        for p in paths:
            print(f"      {p}")


asyncio.run(main())
