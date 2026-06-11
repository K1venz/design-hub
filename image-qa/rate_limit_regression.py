"""A-4 频控 429 回归（dev 8c3c0b2，收敛为 in-flight 一条，dev #594）。

限流落点=post-validation（acquire 在 body422→边界400→owns404→**acquire**→入队，
只有真入队的单计额度）。速率窗口(5/min)由 dev 单测盖死，qa 只验接线+429映射+in-flight 闸：
**2 个真 in-flight job 占满 ≤2 名额 + 第 3 发并发 → 429 不入队不计费**。
一条同时证：429 映射 / in-flight 闸 / acquire 接线（与速率闸共用同一 acquire）。
成本 ¥0.80（2 真单出图、可留数据；第 3 发 429 零成本）。
⚠️ 需 qa 重建含 8c3c0b2 后跑（频控无 openapi 痕迹：频控未上=3 发全 200→本脚本 FAIL=提示频控没生效）。
用法：QA_BASE=http://localhost:8444 uv run python ../image-qa/rate_limit_regression.py
"""

import asyncio
import io
import os
import time

import httpx
from PIL import Image

BASE = os.environ.get("QA_BASE", "").rstrip("/")
SRC = "/Users/Zhuanz/CLAUDE/image-gen/image-qa/通用块多产品/通用块-花生.png"
U = (f"qa-rl-{int(time.time())}@example.com", "qa-rl-123", "QA频控")


def to_png(path: str) -> bytes:
    img = Image.open(path).convert("RGB")
    s = max(img.size)
    cv = Image.new("RGB", (s, s), (255, 255, 255))
    cv.paste(img, ((s - img.width) // 2, (s - img.height) // 2))
    b = io.BytesIO()
    cv.resize((1024, 1024)).save(b, format="PNG")
    return b.getvalue()


async def main() -> None:
    if not BASE:
        raise SystemExit("✋ QA_BASE 未设置。")
    print(f"== A-4 频控 429 回归（in-flight 闸）== BASE={BASE}")
    async with httpx.AsyncClient(base_url=BASE, trust_env=False, timeout=600.0) as c:
        r = await c.post("/auth/register", json={"email": U[0], "password": U[1], "name": U[2]})
        if r.status_code != 200:
            r = await c.post("/auth/login", json={"email": U[0], "password": U[1]})
        tok = r.json()["jwt"]
        H = {"Authorization": f"Bearer {tok}"}
        uid = (await c.post("/uploads", headers=H, files={"file": ("p.png", to_png(SRC), "image/png")})).json()["id"]
        gen = {"upload_ids": [uid], "prompt": "电商主图：产品主体清晰", "ratio": "1:1", "n": 1,
               "category": "FOOD", "modifiers": {"platform": "淘宝天猫1688", "region": "中国", "language": "中文"}}

        async def submit():
            return await c.post("/listing/generate", headers=H, json=gen)

        # 3 发并发：前 2 占满 in-flight(≤2)、第 3 发应 429
        resps = await asyncio.gather(submit(), submit(), submit(), return_exceptions=True)
        codes = sorted(r.status_code if isinstance(r, httpx.Response) else 0 for r in resps)
        jobs = [r.json().get("job_id") for r in resps if isinstance(r, httpx.Response) and r.status_code == 200]
        n200 = sum(1 for x in codes if x == 200)
        n429 = sum(1 for x in codes if x == 429)
        print(f"\n3 发并发状态码={codes}  jobs={jobs}")
        ok = n200 == 2 and n429 == 1
        print(f"  {'PASS' if ok else 'FAIL'}  in-flight 闸：恰 2×200 入队 + 1×429 拒（{n200}×200 / {n429}×429）")
        if not ok and n429 == 0:
            print("  ⚠️ 0 个 429 → 频控可能未生效（qa 未重建含 8c3c0b2？）")
        # 收尾：放掉 2 个真 in-flight（轮询至终态，免悬挂；成本已发生）
        for job in jobs:
            for _ in range(120):
                d = (await c.get(f"/listing/jobs/{job}", headers=H)).json()
                if d.get("status") in ("完成", "失败"):
                    break
                await asyncio.sleep(3)
        print(f"\n==== A-4 频控 429 回归：{'PASS' if ok else 'FAIL'} ====（2 真单 ¥0.80，第 3 发 429 零成本）")


asyncio.run(main())
