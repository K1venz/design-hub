"""通用产品保真块·多产品回归（修「万物皆花生」#366，prompt #373 视觉核标准）。

对每个产品（润喉糖/花生/第三品类）跑 listing 出图（FOOD 通用块），下载落盘供 QA 视觉核：
  ① 非花生产品 → 背景/道具**不出现花生**、不出现任何与产品无关食材/植物/杂物（核心修复点）
  ② 产品本体+包装文字 100% 保留、质感按产品本身真实材质
  ③ 花生产品 → 保真+材质+背景合理即可（不因没「饱满≠滚圆」判 fail，那已入 backlog）
⚠️ 需非花生产品参考图——填进 PRODUCTS（路径待 coordinator/用户给）。
用法：QA_BASE=http://localhost:8444 uv run python ../image-qa/listing_multiproduct_regression.py
"""

import asyncio
import io
import os
import time
from pathlib import Path

import httpx
from PIL import Image

BASE = os.environ.get("QA_BASE", "").rstrip("/")
OUT = Path("/Users/Zhuanz/CLAUDE/image-gen/image-qa/通用块多产品")
A = ("qa-multiprod@example.com", "qa-multiprod-123", "QA多产品回归")

# (label, 产品参考图路径) —— 非花生图路径待 coordinator/用户给后填入
PRODUCTS = [
    ("花生", "/Users/Zhuanz/CLAUDE/image-gen/花生/精修/02aa39d62d25800d3ee14fa91ab42242.jpg"),
    ("润喉糖", "/Users/Zhuanz/Downloads/6e746f45b2cb84cb5eedc38f4b0c7106.jpg"),  # 怀恩堂无糖桉叶油润喉糖(瓶装)·用户测的非花生产品
    # ("第三品类", "<数码/美妆/日用产品图路径，待 coordinator/用户给>"),
]
PROMPT = "电商主图：产品主体清晰、背景干净得体、质感真实突出"
MODIFIERS = {"platform": "淘宝天猫1688", "region": "中国", "language": "中文"}  # 新默认


def to_png(path: str, side: int = 1024) -> bytes:
    img = Image.open(path).convert("RGB")
    s = max(img.size)
    cv = Image.new("RGB", (s, s), (255, 255, 255))
    cv.paste(img, ((s - img.width) // 2, (s - img.height) // 2))
    b = io.BytesIO()
    cv.resize((side, side)).save(b, format="PNG")
    return b.getvalue()


async def run_one(c, H, tok, label, path):  # noqa: ANN001
    uid = (await c.post("/uploads", headers=H, files={"file": ("p.png", to_png(path), "image/png")})).json()["id"]
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
        async with httpx.AsyncClient(trust_env=False, timeout=60.0) as dl:
            resp = await dl.get(imgs[0]["url"])
            fname = f"通用块-{label}.png"
            (OUT / fname).write_bytes(resp.content)
    print(f"[{label}] job={job} {dt}s {evs} → {fname or 'FAIL'}")


async def main() -> None:
    if not BASE:
        raise SystemExit("✋ QA_BASE 未设置。")
    if len(PRODUCTS) < 2:
        print("⚠️ 只有花生图——多产品回归需非花生产品图（润喉糖+第三品类），填进 PRODUCTS 后再跑。")
    OUT.mkdir(exist_ok=True)
    async with httpx.AsyncClient(base_url=BASE, trust_env=False, timeout=600.0) as c:
        r = await c.post("/auth/register", json={"email": A[0], "password": A[1], "name": A[2]})
        if r.status_code != 200:
            r = await c.post("/auth/login", json={"email": A[0], "password": A[1]})
        tok = r.json()["jwt"]
        H = {"Authorization": f"Bearer {tok}"}
        for label, path in PRODUCTS:
            if not Path(path).exists():
                print(f"[{label}] ⚠️ 图不存在: {path} —— 跳过")
                continue
            await run_one(c, H, tok, label, path)
        print(f"\n==== 多产品出图落盘 → {OUT} ====（QA 逐张视觉核：非花生产品无花生背景 + 保真 + 材质真实）")


asyncio.run(main())
