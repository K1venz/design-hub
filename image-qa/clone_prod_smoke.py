"""爆款复刻 prod smoke（高度复刻档，部署后跑）。

验：① 复刻真出图 1 张 ② 落 prod 桶（bucket-design-hub-generate、非 qa）③ clone_mode 回显
④ image_type=null ⑤ cost reconcile（prod 0.40）。落盘 → image-qa/复刻prod_smoke/ 视觉核三命门。
真碰 prod：1 个可标识 qa-test 号 + 1 单复刻（≈¥0.40）。含 SSE 断连降级轮询。
用法：PROD_BASE=http://localhost:8445 uv run python ../image-qa/clone_prod_smoke.py
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
EP = "/listing/clone"
OUT = Path("/Users/Zhuanz/CLAUDE/image-gen/image-qa/复刻prod_smoke")
U = (f"qa-clone-prod-{int(time.time())}@example.com", "qa-clone-prod-123", "QA复刻prodsmoke")
PROD = "/Users/Zhuanz/CLAUDE/image-gen/image-qa/通用块多产品/通用块-花生.png"        # 产品图
REF = "/Users/Zhuanz/CLAUDE/image-gen/image-qa/套图回归/润喉糖-白底.png"            # 爆款模板
MODS = {"platform": "淘宝天猫1688", "region": "中国", "language": "中文"}


def to_png(path: str) -> bytes:
    img = Image.open(path).convert("RGB")
    s = max(img.size)
    cv = Image.new("RGB", (s, s), (255, 255, 255))
    cv.paste(img, ((s - img.width) // 2, (s - img.height) // 2))
    b = io.BytesIO()
    cv.resize((1024, 1024)).save(b, format="PNG")
    return b.getvalue()


async def upload(c, H, path):  # noqa: ANN001
    return (await c.post("/uploads", headers=H, files={"file": ("p.png", to_png(path), "image/png")})).json()["id"]


async def main() -> None:
    if not BASE:
        raise SystemExit("✋ PROD_BASE 未设置——必须经隧道显式指向部署后 prod api。")
    print(f"== 爆款复刻 prod smoke == BASE={BASE}")
    async with httpx.AsyncClient(base_url=BASE, trust_env=False, timeout=600.0) as c:
        op = await c.get("/openapi.json")
        print(f"[probe] openapi {op.status_code}  /clone 上={EP in op.text}")
        if EP not in op.text:
            raise SystemExit("⏳ /listing/clone 未上 prod——等部署。")
        OUT.mkdir(exist_ok=True)
        r = await c.post("/auth/register", json={"email": U[0], "password": U[1], "name": U[2]})
        if r.status_code != 200:
            r = await c.post("/auth/login", json={"email": U[0], "password": U[1]})
        tok = r.json()["jwt"]
        H = {"Authorization": f"Bearer {tok}"}
        pid = await upload(c, H, PROD)
        rid = await upload(c, H, REF)
        bdy = {"product_upload_ids": [pid], "reference_upload_ids": [rid], "clone_mode": "高度复刻",
               "prompt": "电商主图：产品主体清晰、质感真实", "ratio": "1:1", "category": "FOOD", "modifiers": MODS}
        t0 = time.perf_counter()
        job = (await c.post(EP, headers=H, json=bdy)).json()["job_id"]
        try:
            async with c.stream("GET", f"/listing/{job}/events", params={"access_token": tok}) as s:
                ev = None
                async for line in s.aiter_lines():
                    if line.startswith("event:"):
                        ev = line.split(":", 1)[1].strip()
                        if ev in ("task_completed", "task_failed"):
                            break
        except httpx.RemoteProtocolError:
            print(f"  [SSE 断连，降级轮询 job={job}]")
            for _ in range(120):
                jd = (await c.get(f"/listing/jobs/{job}", headers=H)).json()
                if jd.get("status") in ("完成", "失败"):
                    break
                await asyncio.sleep(3)
        dt = int(time.perf_counter() - t0)
        d = (await c.get(f"/listing/jobs/{job}", headers=H)).json()
        imgs = [i for i in d.get("images", []) if i.get("status") == "成功"]
        url = imgs[0]["url"] if imgs else ""
        prod_bucket = bool(url) and "bucket-design-hub-generate" in url and "qa-generate" not in url
        tot = Decimal(str(d.get("total_cost", "0")))
        cost_ok = tot > 0 and tot == sum((Decimal(str(i.get("cost", "0"))) for i in imgs), Decimal("0"))
        if url:
            async with httpx.AsyncClient(trust_env=False, timeout=60.0) as dl:
                resp = await dl.get(url)
                if resp.status_code == 200:
                    (OUT / "prod-复刻-高度复刻-花生×润喉糖模板.png").write_bytes(resp.content)
        print(f"\n==== 复刻 prod smoke ==== job={job} {dt}s status={d.get('status')} clone_mode={d.get('clone_mode')} roles={d.get('input_roles')} cost={tot}")
        print(f"① 复刻真出图 1 张 : {'PASS' if d.get('status') == '完成' and len(imgs) == 1 else 'FAIL'}")
        print(f"② 落 prod 桶      : {'PASS' if prod_bucket else 'FAIL'}  url={url[:90]}")
        print(f"③ clone_mode 回显 : {'PASS' if d.get('clone_mode') == '高度复刻' else 'FAIL'}")
        print(f"④ image_type=null : {'PASS' if imgs and imgs[0].get('image_type') in (None, '') else 'FAIL'}")
        print(f"⑤ cost reconcile  : {'PASS' if cost_ok else 'FAIL'}")
        print(f"\n落盘视觉核三命门（产物=花生保真/无润喉糖泄漏/无糊文案）→ {OUT}。qa-test 号 {U[0]} 可后清。")


asyncio.run(main())
