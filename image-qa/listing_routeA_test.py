"""路 A 实测（coordinator #394 批准 / prompt #392 判读口径）。

问题：花生 styling（散落带壳花生 + 紫罗兰七彩花生米）该走
  路 A = 用户 prompt 自己写散落花生，靠通用块兜底  还是
  路 B = product-level 花生专属块。
本测验证路 A 可靠性：花生产品 + 用户 prompt 显式写「周围散落带壳花生 + 紫罗兰七彩花生米」，
看通用块的「严禁堆砌无关食材」会不会把这个**与产品相关**的请求压住。
  判读：散落花生/紫米出来 → 路 A 可靠兜底；被压住不出 → 路 A 不稳，走路 B。
只测花生（润喉糖 #386 已证非花生产品不泄漏花生）。¥0.40、qa env、n=1。
用法：QA_BASE=http://localhost:8444 uv run python ../image-qa/listing_routeA_test.py
"""

import asyncio
import io
import os
import time
from pathlib import Path

import httpx

from qa_auth import login_verified_account
from PIL import Image

BASE = os.environ.get("QA_BASE", "").rstrip("/")
SRC = "/Users/Zhuanz/CLAUDE/image-gen/花生/精修/02aa39d62d25800d3ee14fa91ab42242.jpg"
OUT = Path("/Users/Zhuanz/CLAUDE/image-gen/image-qa/路A实测")
PROMPT = (
    "电商主图：颗粒饱满的花生产品，主体清晰、背景干净得体、质感真实突出；"
    "周围散落一些带壳花生与紫罗兰色七彩花生米作点缀，营造丰收质感"
)
MODIFIERS = {"platform": "淘宝天猫1688", "region": "中国", "language": "中文"}  # 新默认


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
        raise SystemExit("✋ QA_BASE 未设置。")
    print(f"== 路A实测 == BASE={BASE}")
    async with httpx.AsyncClient(base_url=BASE, trust_env=False, timeout=600.0) as c:
        print(f"[probe] openapi {(await c.get('/openapi.json')).status_code}")
        session = await login_verified_account(c)
        tok = session.jwt
        H = {"Authorization": f"Bearer {tok}"}
        uid = (await c.post("/uploads", headers=H, files={"file": ("p.png", to_png(SRC), "image/png")})).json()["id"]
        body = {"upload_ids": [uid], "prompt": PROMPT, "ratio": "1:1", "n": 1, "category": "FOOD", "modifiers": MODIFIERS}
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
        imgs = [im for im in d.get("images", []) if im.get("status") == "成功"]
        fname = ""
        if imgs:
            OUT.mkdir(exist_ok=True)
            async with httpx.AsyncClient(trust_env=False, timeout=60.0) as dl:
                resp = await dl.get(imgs[0]["url"])
                fname = "路A-花生-散落紫米.png"
                (OUT / fname).write_bytes(resp.content)
        print(f"\n==== 路A实测 ====")
        print(f"job={job} {dt}s status={d.get('status')} {evs} cost={d.get('total_cost')}")
        print(f"prompt={PROMPT}")
        print(f"落盘 → {OUT / fname if fname else 'FAIL'}")
        print(f"判读：QA 视觉核 → 散落带壳花生/紫米出来=路A可靠；被压住不出=路A不稳走路B")


asyncio.run(main())
