"""prod smoke（花生卡上线 step7，coordinator #246）——部署后 prod 真出图烟测。

category=FOOD 真出图三查：① 非401·真出图 ② 落 prod 桶 ③ 花生卡生效(下载视觉核)。
⚠️ 部署后 prod 也是 platform 7→4 → 用国内 **抖音电商**(亚马逊已删→400)；category=FOOD。
⚠️ 真碰 prod：运行时已验证账号 + 1 张 n=1 落 prod 桶；不注册、不发邮件，作业 footprint 可后清。
PROD_BASE 经隧道指 prod api 容器（ops 部署后起）。
用法：PROD_BASE=http://localhost:8445 uv run python ../image-qa/listing_prod_smoke.py
"""

import asyncio
import io
import os
import time
from pathlib import Path

import httpx

from qa_auth import login_verified_account
from PIL import Image

BASE = os.environ.get("PROD_BASE", "").rstrip("/")
SRC = "/Users/Zhuanz/CLAUDE/image-gen/花生/精修/02aa39d62d25800d3ee14fa91ab42242.jpg"
OUT = Path("/Users/Zhuanz/CLAUDE/image-gen/image-qa/花生提示词AB")
def to_png(path: str, side: int = 1024) -> bytes:
    img = Image.open(path).convert("RGB")
    s = max(img.size)
    cv = Image.new("RGB", (s, s), (255, 255, 255))
    cv.paste(img, ((s - img.width) // 2, (s - img.height) // 2))
    b = io.BytesIO()
    cv.resize((side, side)).save(b, format="PNG")
    return b.getvalue()


async def main() -> None:
    if not BASE:
        raise SystemExit("✋ PROD_BASE 未设置——必须经隧道显式指向部署后的 prod api。")
    print(f"== prod smoke (花生卡上线) == BASE={BASE}")
    async with httpx.AsyncClient(base_url=BASE, trust_env=False, timeout=600.0) as c:
        op = await c.get("/openapi.json")
        print(f"[probe] openapi {op.status_code} · category 字段在={'category' in op.text}（部署后应=True）")
        session = await login_verified_account(c)
        tok = session.jwt
        H = {"Authorization": f"Bearer {tok}"}
        # 顺带烟测 platform 收窄已上 prod：亚马逊→400
        rj = await c.post("/listing/generate", headers=H,
                          json={"upload_ids": ["0000000000000000.png"], "prompt": "x", "ratio": "1:1", "n": 1,
                                "modifiers": {"platform": "亚马逊"}, "category": "FOOD"})
        amazon_gone = rj.status_code == 400
        uid = (await c.post("/uploads", headers=H, files={"file": ("p.png", to_png(SRC), "image/png")})).json()["id"]
        body = {"upload_ids": [uid], "prompt": "电商主图：颗粒饱满的花生产品，主体清晰、背景干净、质感突出",
                "ratio": "1:1", "n": 1, "modifiers": {"platform": "抖音电商"}, "category": "FOOD"}
        t0 = time.perf_counter()
        job = (await c.post("/listing/generate", headers=H, json=body)).json()["job_id"]
        evs = []
        async with c.stream("GET", f"/listing/{job}/events", params={"access_token": tok}) as s:
            async for line in s.aiter_lines():
                if line.startswith("event:"):
                    et = line.split(":", 1)[1].strip()
                    evs.append(et)
                    if et in ("task_completed", "task_failed"):
                        break
        dt = int(time.perf_counter() - t0)
        d = (await c.get(f"/listing/jobs/{job}", headers=H)).json()
        imgs = d.get("images", [])
        url = imgs[0]["url"] if imgs else ""
        ok = "task_completed" in evs
        prod_bucket = "bucket-design-hub-generate" in url and "qa-generate" not in url
        if imgs and url:
            async with httpx.AsyncClient(trust_env=False, timeout=60.0) as dl:
                resp = await dl.get(url)
                if resp.status_code == 200:
                    OUT.mkdir(exist_ok=True)
                    (OUT / "prod-smoke-category=FOOD.png").write_bytes(resp.content)
        print("\n==== prod smoke 三查 ====")
        print(f"① 非401·真出图 : {'PASS' if ok else 'FAIL'}  job={job} {dt}s status={d.get('status')} {evs} cost={d.get('total_cost')}")
        print(f"② 落点=prod桶  : {'PASS' if prod_bucket else 'FAIL'}  url={url[:110]}")
        print(f"③ 卡生效       : 落盘 prod-smoke-category=FOOD.png — QA 视觉核(饱满真实不圆+包装保真)")
        print(f"附 platform 收窄上 prod: 亚马逊→400 = {'PASS' if amazon_gone else 'FAIL(亚马逊仍合法?)'}")
        print(f"\njob={job} 已验证账号 {session.email} 保留；仅清理本次 job/image footprint。")


asyncio.run(main())
