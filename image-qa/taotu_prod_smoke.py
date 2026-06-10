"""套图 prod smoke（默认套图 1/2/2=5 张，部署后跑）。

验：① 默认套图真出图 5 张 ② image_type 分布=白底1/场景2/卖点2 ③ **落 prod 桶**
（bucket-design-hub-generate、非 qa）④ 无 image_failed ⑤ cost reconcile（prod 应 0.40/张）。
落盘 → image-qa/套图prod_smoke/ 逐张视觉核（保真+图型像型）。
真碰 prod：1 个可标识 qa-test 号 + 默认 5 张（≈¥2、coordinator/PRD 批的默认配置真跑铁律）。
用法：PROD_BASE=http://localhost:8445 uv run python ../image-qa/taotu_prod_smoke.py
"""

import asyncio
import io
import json
import os
import time
from decimal import Decimal
from pathlib import Path

import httpx
from PIL import Image

BASE = os.environ.get("PROD_BASE", "").rstrip("/")
SRC = "/Users/Zhuanz/CLAUDE/image-gen/image-qa/通用块多产品/通用块-花生.png"
OUT = Path("/Users/Zhuanz/CLAUDE/image-gen/image-qa/套图prod_smoke")
U = (f"qa-taotu-prod-{int(time.time())}@example.com", "qa-taotu-prod-123", "QA套图prodsmoke")
PLAN = {"白底": 1, "场景": 2, "卖点": 2}


def to_png(p):  # noqa: ANN001
    img = Image.open(p).convert("RGB")
    s = max(img.size)
    cv = Image.new("RGB", (s, s), (255, 255, 255))
    cv.paste(img, ((s - img.width) // 2, (s - img.height) // 2))
    b = io.BytesIO()
    cv.resize((1024, 1024)).save(b, format="PNG")
    return b.getvalue()


async def main():  # noqa: ANN001
    if not BASE:
        raise SystemExit("✋ PROD_BASE 未设置——必须经隧道显式指向部署后 prod api。")
    OUT.mkdir(exist_ok=True)
    print(f"== 套图 prod smoke == BASE={BASE}")
    async with httpx.AsyncClient(base_url=BASE, trust_env=False, timeout=900.0) as c:
        print(f"[probe] openapi {(await c.get('/openapi.json')).status_code}")
        r = await c.post("/auth/register", json={"email": U[0], "password": U[1], "name": U[2]})
        if r.status_code != 200:
            r = await c.post("/auth/login", json={"email": U[0], "password": U[1]})
        tok = r.json()["jwt"]
        H = {"Authorization": f"Bearer {tok}"}
        uid = (await c.post("/uploads", headers=H, files={"file": ("p.png", to_png(SRC), "image/png")})).json()["id"]
        body = {"upload_ids": [uid], "prompt": "电商主图：产品主体清晰、背景干净得体、质感真实突出",
                "ratio": "1:1", "category": "FOOD",
                "modifiers": {"platform": "淘宝天猫1688", "region": "中国", "language": "中文"}, "plan": PLAN}
        t0 = time.perf_counter()
        job = (await c.post("/listing/generate", headers=H, json=body)).json()["job_id"]
        evs = []
        async with c.stream("GET", f"/listing/{job}/events", params={"access_token": tok}) as s:
            ev = None
            async for line in s.aiter_lines():
                if line.startswith("event:"):
                    ev = line.split(":", 1)[1].strip()
                elif line.startswith("data:") and ev:
                    evs.append(ev)
                    if ev in ("task_completed", "task_failed"):
                        break
        dt = int(time.perf_counter() - t0)
        d = (await c.get(f"/listing/jobs/{job}", headers=H)).json()
        imgs = [i for i in d.get("images", []) if i.get("status") == "成功"]
        dist = sorted(i.get("image_type") or "?" for i in imgs)
        prod_bucket = all("bucket-design-hub-generate" in i["url"] and "qa-generate" not in i["url"] for i in imgs) if imgs else False
        tot = Decimal(str(d.get("total_cost", "0")))
        cost_ok = tot > 0 and tot == sum((Decimal(str(i.get("cost", "0"))) for i in imgs), Decimal("0"))
        for i in imgs:
            t = i.get("image_type")
            async with httpx.AsyncClient(trust_env=False, timeout=60.0) as dl:
                resp = await dl.get(i["url"])
                if resp.status_code == 200:
                    (OUT / f"prod-{t}-{i['url'].split('/')[-1][:8]}.png").write_bytes(resp.content)
        print(f"\n==== 套图 prod smoke ==== job={job} {dt}s status={d.get('status')} cost={d.get('total_cost')}")
        print(f"① 默认套图 5 张真出图 : {'PASS' if d.get('status') == '完成' and len(imgs) == 5 else 'FAIL'}  ({len(imgs)} 成功张)")
        print(f"② 分布=白底1/场景2/卖点2 : {'PASS' if dist == ['卖点', '卖点', '场景', '场景', '白底'] else 'FAIL'}  got {dist}")
        print(f"③ 落 prod 桶            : {'PASS' if prod_bucket else 'FAIL'}")
        print(f"④ 无 image_failed       : {'PASS' if 'image_failed' not in evs else 'FAIL'}")
        print(f"⑤ cost reconcile(>0)    : {'PASS' if cost_ok else 'FAIL'}  total={tot}")
        print(f"\n落盘 → {OUT}（QA 逐张视觉核：保真+图型像型）。qa-test 号 {U[0]} 可后清（ops）。")


asyncio.run(main())
