"""二次编辑 + ISSUE-0045 prod smoke（部署后跑，0040+284ce82 一把上）。

⚠️ prod 直连 = **8446**（→172.19.0.2 prod api，ops 起；8445 是 qa）。
验：① base n=1 真出图=**恰 1 图**（0045 修上 prod 确认不双图）② delta 编辑 1 张
③ edit_mode=delta 回显 + parent 链 ④ chain_cost（根算源张单张）⑤ 落 prod 桶。
落盘 base+edit 视觉核（链根锚：编辑产品保真）。真碰 prod：1 qa-test 号 + 2 单 ≈¥0.80。
用法：PROD_BASE=http://localhost:8446 uv run python ../image-qa/edit_prod_smoke.py
"""

import asyncio
import io
import os
import time
from decimal import Decimal
from pathlib import Path

import httpx
from PIL import Image

BASE = os.environ.get("PROD_BASE", "").rstrip("/")
SRC = "/Users/Zhuanz/CLAUDE/image-gen/image-qa/通用块多产品/通用块-花生.png"
OUT = Path("/Users/Zhuanz/CLAUDE/image-gen/image-qa/二次编辑prod_smoke")
U = (f"qa-edit-prod-{int(time.time())}@example.com", "qa-edit-prod-123", "QA编辑prodsmoke")


def to_png(path: str) -> bytes:
    img = Image.open(path).convert("RGB")
    s = max(img.size)
    cv = Image.new("RGB", (s, s), (255, 255, 255))
    cv.paste(img, ((s - img.width) // 2, (s - img.height) // 2))
    b = io.BytesIO()
    cv.resize((1024, 1024)).save(b, format="PNG")
    return b.getvalue()


async def wait(c, H, tok, job):  # noqa: ANN001
    try:
        async with c.stream("GET", f"/listing/{job}/events", params={"access_token": tok}) as s:
            ev = None
            async for line in s.aiter_lines():
                if line.startswith("event:"):
                    ev = line.split(":", 1)[1].strip()
                    if ev in ("task_completed", "task_failed"):
                        break
    except httpx.RemoteProtocolError:
        pass
    for _ in range(150):
        d = (await c.get(f"/listing/jobs/{job}", headers=H)).json()
        if d.get("status") in ("完成", "失败"):
            return d
        await asyncio.sleep(3)
    return (await c.get(f"/listing/jobs/{job}", headers=H)).json()


async def dl(img, fname):  # noqa: ANN001
    if not img:
        return False
    async with httpx.AsyncClient(trust_env=False, timeout=60.0) as d:
        r = await d.get(img["url"])
        if r.status_code == 200:
            (OUT / fname).write_bytes(r.content)
            return True
    return False


def prod_bucket(img):  # noqa: ANN001
    u = img.get("url", "") if img else ""
    return "bucket-design-hub-generate" in u and "qa-generate" not in u


async def main() -> None:
    if not BASE:
        raise SystemExit("✋ PROD_BASE 未设置——prod 直连须 8446（非 8445=qa）。")
    OUT.mkdir(exist_ok=True)
    print(f"== 二次编辑 + 0045 prod smoke == BASE={BASE}")
    async with httpx.AsyncClient(base_url=BASE, trust_env=False, timeout=900.0) as c:
        r = await c.post("/auth/register", json={"email": U[0], "password": U[1], "name": U[2]})
        if r.status_code != 200:
            r = await c.post("/auth/login", json={"email": U[0], "password": U[1]})
        tok = r.json()["jwt"]
        H = {"Authorization": f"Bearer {tok}"}
        if (await c.post("/listing/edit", headers=H, json={})).status_code == 404:
            raise SystemExit("⏳ /listing/edit 未上 prod——等部署。")
        uid = (await c.post("/uploads", headers=H, files={"file": ("p.png", to_png(SRC), "image/png")})).json()["id"]
        # ① base n=1（0045：恰 1 图）
        gen = {"upload_ids": [uid], "prompt": "电商主图：产品主体清晰", "ratio": "1:1", "n": 1,
               "category": "FOOD", "modifiers": {"platform": "淘宝天猫1688", "region": "中国", "language": "中文"}}
        jb = (await c.post("/listing/generate", headers=H, json=gen)).json()["job_id"]
        db = await wait(c, H, tok, jb)
        bimgs = [i for i in db.get("images", []) if i.get("status") == "成功"]
        bkey = bimgs[0].get("image_key") if bimgs else None
        await dl(bimgs[0] if bimgs else None, "0-base.png")
        # ② delta 编辑
        edit = {"source_image_key": bkey, "edit_mode": "delta", "prompt": "把背景换成纯白",
                "modifiers": gen["modifiers"]}
        re = await c.post("/listing/edit", headers=H, json=edit)
        de = await wait(c, H, tok, re.json()["job_id"]) if re.status_code == 200 else {}
        eimgs = [i for i in de.get("images", []) if i.get("status") == "成功"]
        await dl(eimgs[0] if eimgs else None, "1-delta编辑.png")
        cc = de.get("chain_cost")
        print("\n==== 二次编辑 + 0045 prod smoke ====")
        print(f"① base n=1 恰 1 图（0045 修）: {'PASS' if db.get('status') == '完成' and len(bimgs) == 1 else 'FAIL'}  (status={db.get('status')} 图={len(bimgs)} cost={db.get('total_cost')})")
        print(f"② delta 编辑 1 图          : {'PASS' if re.status_code == 200 and de.get('status') == '完成' and len(eimgs) == 1 else 'FAIL'}  (http={re.status_code} status={de.get('status')})")
        print(f"③ edit_mode=delta + parent : {'PASS' if de.get('edit_mode') == 'delta' and de.get('parent_job_id') else 'FAIL'}")
        print(f"④ chain_cost 根算源张       : {'PASS' if cc is not None and Decimal(str(cc or 0)) > 0 else 'FAIL'}  (chain_cost={cc})")
        print(f"⑤ base+edit 落 prod 桶      : {'PASS' if prod_bucket(bimgs[0] if bimgs else None) and prod_bucket(eimgs[0] if eimgs else None) else 'FAIL'}")
        print(f"\n落盘视觉核（编辑产品保真·链根锚）→ {OUT}。qa-test 号 {U[0]} 可后清。")


asyncio.run(main())
