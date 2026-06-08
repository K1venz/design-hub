"""花生优化版提示词（coordinator #197）：包装绝对不动 + 花生饱满真实(防"太圆")。

设置同"新"：单张精修参考、同场景、亚马逊 1:1，只换优化版 prompt 块。
落盘 image-qa/花生提示词AB/优化版-饱满真实.png。qa n=1 ≈ $0.05。
用法：QA_BASE=http://localhost:8444 uv run python ../image-qa/listing_peanut_opt.py
"""

import asyncio
import io
import os
import time
from pathlib import Path

import httpx
from PIL import Image

BASE = os.environ.get("QA_BASE", "").rstrip("/")
SRC = "/Users/Zhuanz/CLAUDE/image-gen/花生/精修/02aa39d62d25800d3ee14fa91ab42242.jpg"
OUT = Path("/Users/Zhuanz/CLAUDE/image-gen/image-qa/花生提示词AB")
A = ("qa-acc-a@example.com", "qa-acc-a-123", "验收用户A")

OPT = (
    "包装绝对保真：上传参考图里的产品包装(袋型、配色、白熊图案、袋面所有文字与排版)100% 原样保留——"
    "一个字、一个像素都不改、不重画、不翻译；只重绘包装周围的背景、道具与光线。"
    "花生饱满+真实：花生果仁粒大饱满、充实鼓胀、有真实的体积感与重量感，像刚剥开的新鲜花生那样鼓实有肉；"
    "七彩花生米保持紫罗兰/紫红+奶白大理石纹本色、果实白亮。表面整体哑光干爽、仅极轻微自然油润，"
    "严禁糖浆高光/油亮反光/塑料光泽；带壳花生保持土黄硬壳与清晰网状脉络。"
    "饱满≠光滑滚圆：果形自然不规则、有壳尖、深浅不均、表面带细褶皱，不要完美对称光滑圆球；"
    "颗粒大小不一、自然随意散落，允许个别开口带壳露米/双仁。"
    "光与镜头：50mm f/2.8 近景浅景深，侧前方自然漫射光勾出果粒饱满体积与凹凸、柔中带方向性硬阴影、"
    "与台面真实接触阴影；前景花生锐利可见脉络。"
    "画面禁止：改动/重画/翻译产品包装、塑料感、糖浆高光、油亮反光、干瘪瘦小的花生、过度鲜艳饱和、"
    "完美整齐排列、人物/水印/多余商品。"
)
SCENE = "电商主图：颗粒饱满的花生产品，主体清晰、背景干净、质感突出"
MODIFIERS = {"platform": "亚马逊", "region": "美国", "language": "英文"}


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
        raise SystemExit("✋ QA_BASE 必须指向 server qa 实例。")
    OUT.mkdir(exist_ok=True)
    async with httpx.AsyncClient(base_url=BASE, trust_env=False, timeout=600.0) as c:
        r = await c.post("/auth/register", json={"email": A[0], "password": A[1], "name": A[2]})
        if r.status_code != 200:
            r = await c.post("/auth/login", json={"email": A[0], "password": A[1]})
        tok = r.json()["jwt"]
        H = {"Authorization": f"Bearer {tok}"}
        uid = (await c.post("/uploads", headers=H, files={"file": ("p.png", to_png(SRC), "image/png")})).json()["id"]
        body = {"upload_ids": [uid], "prompt": OPT + "\n" + SCENE, "ratio": "1:1", "n": 1, "modifiers": MODIFIERS}
        for attempt in range(1, 3):
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
            print(f"[优化版] 第{attempt}次 job={job} {int(time.perf_counter()-t0)}s {evs}")
            if "task_completed" in evs:
                break
        d = (await c.get(f"/listing/jobs/{job}", headers=H)).json()
        imgs = [im for im in d.get("images", []) if im.get("status") == "成功"]
        if imgs:
            async with httpx.AsyncClient(trust_env=False, timeout=60.0) as dl:
                resp = await dl.get(imgs[0]["url"])
                (OUT / "优化版-饱满真实.png").write_bytes(resp.content)
                print(f"[优化版] 落盘 优化版-饱满真实.png ({len(resp.content)//1024} KB)")
        print(f"\n==== 优化版 落盘 → {OUT} ====")


asyncio.run(main())
