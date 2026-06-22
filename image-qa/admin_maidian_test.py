"""用户选1:套图卖点图+overlay_texts 出「带角标爆款主图」(对比复刻迁移不到版式)。

登录 admin(creds 从 env)→ 1 个套图 job:产品=花生、plan={卖点:3}(3 张卖点图变体)、
overlay_texts=用户爆款图的卖点词(系统上限 2 条/图:清脆爽口+甘香回甜;拒绝添加超限,另跑)。
= 卖点图把卖点文案 verbatim 排版上图 = 带角标爆款主图(复刻做不到的图形版式,这条路能)。
成品落 image-qa/admin卖点test/、打印路径+job/cost。
用法：PROD_BASE=https://203.0.113.10 API_PREFIX=/api ADMIN_EMAIL=... ADMIN_PASSWORD=... \
      [OVERLAY='清脆爽口,甘香回甜'] uv run python ../image-qa/admin_maidian_test.py
"""

import asyncio
import io
import os
import time
from decimal import Decimal
from pathlib import Path

import httpx
from PIL import Image

BASE = (os.environ.get("PROD_BASE") or os.environ.get("QA_BASE") or "").rstrip("/")
PREFIX = os.environ.get("API_PREFIX", "").rstrip("/")
EMAIL = os.environ.get("ADMIN_EMAIL", "")
PASSWORD = os.environ.get("ADMIN_PASSWORD", "")
OVERLAY = [t for t in os.environ.get("OVERLAY", "清脆爽口,甘香回甜").split(",") if t.strip()]
OUT = Path("/Users/Zhuanz/CLAUDE/image-gen/image-qa/admin卖点test")
PRODUCT = "/Users/Zhuanz/CLAUDE/image-gen/image-qa/通用块多产品/通用块-花生.png"
MODS = {"platform": "淘宝天猫1688", "region": "中国", "language": "中文"}
PLAN = {"卖点": 3}  # 3 张卖点图变体（总数 3 合规）


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


async def main() -> None:
    if not (BASE and EMAIL and PASSWORD):
        raise SystemExit("✋ 需 PROD_BASE/ADMIN_EMAIL/ADMIN_PASSWORD。")
    OUT.mkdir(exist_ok=True)
    print(f"== admin 卖点图(带角标)实测 == BASE={BASE}{PREFIX or ''} 账号={EMAIL}")
    print(f"   产品=花生  plan={PLAN}  overlay_texts={OVERLAY}")
    async with httpx.AsyncClient(base_url=BASE, trust_env=False, verify=False, timeout=900.0) as c:
        r = await c.post(f"{PREFIX}/auth/login", json={"email": EMAIL, "password": PASSWORD})
        if r.status_code != 200:
            raise SystemExit(f"🔴 登录失败 {r.status_code}: {r.text[:200]}")
        tok = r.json()["jwt"]
        H = {"Authorization": f"Bearer {tok}"}
        print(f"  登录成功 role={r.json().get('role')} name={r.json().get('name')}")
        uid = (await c.post(f"{PREFIX}/uploads", headers=H, files={"file": ("p.png", to_png(PRODUCT), "image/png")})).json()["id"]
        body = {"upload_ids": [uid], "prompt": "电商主图：产品主体清晰、背景干净得体、质感真实突出",
                "ratio": "1:1", "category": "FOOD", "modifiers": MODS, "plan": PLAN, "overlay_texts": OVERLAY}
        t0 = time.perf_counter()
        job = (await c.post(f"{PREFIX}/listing/generate", headers=H, json=body)).json()["job_id"]
        d = await wait_job(c, H, tok, job)
        dt = int(time.perf_counter() - t0)
        imgs = [i for i in d.get("images", []) if i.get("status") == "成功"]
        tot = Decimal(str(d.get("total_cost", "0")))
        print(f"\n[卖点图×{len(imgs)}] job={job} {dt}s status={d.get('status')} cost=¥{tot}")
        paths = []
        for n, i in enumerate(imgs, 1):
            async with httpx.AsyncClient(trust_env=False, verify=False, timeout=60.0) as dl:
                resp = await dl.get(i["url"])
                if resp.status_code == 200:
                    p = str(OUT / f"卖点-{'_'.join(OVERLAY)}-{n}.png")
                    Path(p).write_bytes(resp.content)
                    paths.append(p)
        for p in paths:
            print(f"   {p}")
        print(f"\n==== 卖点图带角标:{len(paths)} 张 / ¥{tot} / overlay={OVERLAY} ====")


asyncio.run(main())
