"""prod 真出图复验（listing 上线硬 gate，coordinator #207）。

ops 换 prod key+model→base+重建 后跑。三查：① 非 401、真出图 ② 落点=prod 桶/库(非 qa) ③ 档位=base。
⚠️ 真碰 prod：1 个 qa-test 用户 + 1 张 n=1 出图(落 prod 桶、本就该)，footprint 最小、可标识、可后清。
PROD_BASE 经隧道指 prod api 容器（ops 起 ssh -L <口>:<prod_api_ip>:8000）。
用法：PROD_BASE=http://localhost:8445 uv run python ../image-qa/listing_prod_verify.py
"""

import asyncio
import io
import os
import time

import httpx
from PIL import Image

BASE = os.environ.get("PROD_BASE", "").rstrip("/")
SRC = "/Users/Zhuanz/CLAUDE/image-gen/花生/精修/02aa39d62d25800d3ee14fa91ab42242.jpg"
U = ("qa-prod-verify@example.com", "qa-prod-verify-123", "QA上线复验")


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
        raise SystemExit("✋ PROD_BASE 未设置——必须经隧道显式指向 prod api。")
    print(f"== prod 真出图复验 == BASE={BASE}")
    async with httpx.AsyncClient(base_url=BASE, trust_env=False, timeout=600.0) as c:
        # 安全确认：先打 openapi 确认通
        op = await c.get("/openapi.json")
        print(f"[probe] openapi HTTP {op.status_code}")
        r = await c.post("/auth/register", json={"email": U[0], "password": U[1], "name": U[2]})
        if r.status_code != 200:
            r = await c.post("/auth/login", json={"email": U[0], "password": U[1]})
        tok = r.json()["jwt"]
        H = {"Authorization": f"Bearer {tok}"}
        uid = (await c.post("/uploads", headers=H, files={"file": ("p.png", to_png(SRC), "image/png")})).json()["id"]
        body = {"upload_ids": [uid], "prompt": "电商主图：颗粒饱满的花生产品，主体清晰、背景干净、质感突出",
                "ratio": "1:1", "n": 1, "modifiers": {"platform": "亚马逊", "region": "美国", "language": "英文"}}
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
        input_url = (d.get("input_urls") or [""])[0]
        ok = "task_completed" in evs
        # 三查
        check1 = ok  # 非 401、真出图
        check2 = "bucket-design-hub-generate" in url and "qa-generate" not in url  # 落点 prod 桶(非 qa)
        print("\n==== 三查 ====")
        print(f"① 非401·真出图 : {'PASS' if check1 else 'FAIL'}  job={job} {dt}s status={d.get('status')} events={evs} cost={d.get('total_cost')}")
        print(f"② 落点=prod桶  : {'PASS' if check2 else 'FAIL'}  输出url={url[:120]}")
        print(f"   (输入图url   : {input_url[:120]})")
        print(f"③ 档位=base    : 见 SSH 查 prod 容器 GPT_IMAGE_MODEL=gpt-image-2（脚本外确认）")
        print(f"\njob={job} 输出图key可在 prod 桶/库核；qa-test 用户 {U[0]} 可后清。")


asyncio.run(main())
