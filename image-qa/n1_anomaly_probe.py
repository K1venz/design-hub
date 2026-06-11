"""ISSUE-0045 资损修验证探针（n=1 张数契约核，dev 284ce82）。

修前：`_parse` 无 n==len(data) 核，中转站对 n=1 偶发返 2 项 → 落 2 图计双倍费（资损）。
修后：`len(data)!=expected_n → ProviderError` fail-fast（回滚不计费、整单 TASK_FAILED）。
探针：跑 N 个 n=1 gen，每单断言 **NEVER 2 图 + 计费=图数×单价**：
  · 完成 → 恰 1 图、cost=1×单价（正常，不回归）
  · 失败 → 0 图、cost=0（修触发=中转站违约被 fail-fast 挡、不双计费）
  ⚠️ 违约偶发不可强制——本探针验「修后正常 n=1 不回归 + 结构上不可能 2 图」；违约分支由 dev 单测(48绿)盖。
⚠️ 需 qa 重建含 284ce82 后跑。用法：QA_BASE=http://localhost:8444 N=3 uv run python ../image-qa/n1_anomaly_probe.py
"""

import asyncio
import io
import os
import time
from decimal import Decimal

import httpx
from PIL import Image

BASE = os.environ.get("QA_BASE", "").rstrip("/")
N = int(os.environ.get("N", "3"))
SRC = "/Users/Zhuanz/CLAUDE/image-gen/image-qa/通用块多产品/通用块-花生.png"
U = (f"qa-n1-{int(time.time())}@example.com", "qa-n1-123", "QA资损探针")


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
    for _ in range(120):
        d = (await c.get(f"/listing/jobs/{job}", headers=H)).json()
        if d.get("status") in ("完成", "失败"):
            return d
        await asyncio.sleep(3)
    return (await c.get(f"/listing/jobs/{job}", headers=H)).json()


async def main() -> None:
    if not BASE:
        raise SystemExit("✋ QA_BASE 未设置。")
    print(f"== ISSUE-0045 n=1 资损探针 (284ce82) == BASE={BASE} N={N}")
    async with httpx.AsyncClient(base_url=BASE, trust_env=False, timeout=600.0) as c:
        r = await c.post("/auth/register", json={"email": U[0], "password": U[1], "name": U[2]})
        if r.status_code != 200:
            r = await c.post("/auth/login", json={"email": U[0], "password": U[1]})
        tok = r.json()["jwt"]
        H = {"Authorization": f"Bearer {tok}"}
        uid = (await c.post("/uploads", headers=H, files={"file": ("p.png", to_png(SRC), "image/png")})).json()["id"]
        body = {"upload_ids": [uid], "prompt": "电商主图：产品主体清晰", "ratio": "1:1", "n": 1,
                "category": "FOOD", "modifiers": {"platform": "淘宝天猫1688", "region": "中国", "language": "中文"}}
        npass = 0
        for i in range(1, N + 1):
            job = (await c.post("/listing/generate", headers=H, json=body)).json()["job_id"]
            d = await wait(c, H, tok, job)
            imgs = d.get("images", [])
            ok_imgs = [im for im in imgs if im.get("status") == "成功"]
            status = d.get("status")
            cost = Decimal(str(d.get("total_cost", "0")))
            # 核心断言：NEVER 2 图；完成→1图/cost=单图、失败→0图/cost=0；计费=成功图数
            ncount = len(ok_imgs)
            never2 = ncount <= 1
            cost_match = cost == sum((Decimal(str(im.get("cost", "0"))) for im in ok_imgs), Decimal("0"))
            consistent = (status == "完成" and ncount == 1) or (status == "失败" and ncount == 0)
            ok = never2 and cost_match and consistent
            npass += ok
            print(f"  {'PASS' if ok else '🔴 FAIL'}  job={job[:12]} status={status} 成功图={ncount} cost={cost}"
                  + ("" if never2 else "  <<< 2 图！资损复现！"))
        print(f"\n==== ISSUE-0045 n=1 探针：{npass}/{N} ====（NEVER 2 图 + 计费=图数；修后正常 n=1 不回归）")


asyncio.run(main())
