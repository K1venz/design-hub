"""套图真出图回归（骨架 TT-01/02/03/09/13/15/18/20 真图侧）。

三单：① 花生 plan 1/1/1 + overlay 2 条（TT-15 verbatim、标签分布、SSE image_type）
② 润喉糖 plan 1/1/1 无 overlay（TT-18 无字 + T4 矩阵非花生半边：防图型卡版万物皆花生）
③ 花生 n=1 单图流（TT-20 零破坏：完成 + image_type 为空）
成本：7 张 × ¥0.40 = ¥2.80（qa 价已与 prod 同口径，ops #503）。落盘 → image-qa/套图回归/ 逐张视觉核。
用法：QA_BASE=http://localhost:8444 uv run python ../image-qa/taotu_real_regression.py
"""

import asyncio
import io
import json
import os
import time
from pathlib import Path

import httpx
from PIL import Image

BASE = os.environ.get("QA_BASE", "").rstrip("/")
OUT = Path("/Users/Zhuanz/CLAUDE/image-gen/image-qa/套图回归")
U = (f"qa-taotu-r-{int(time.time())}@example.com", "qa-taotu-123", "QA套图真图")
# 原精修花生图目录已被移走（2026-06-10 发现）；改用 QA 已落盘的通用块回归产物作源（含完整产品袋，保真核基线=该袋）
PEANUT = "/Users/Zhuanz/CLAUDE/image-gen/image-qa/通用块多产品/通用块-花生.png"
LOZENGE = "/Users/Zhuanz/Downloads/6e746f45b2cb84cb5eedc38f4b0c7106.jpg"
MODS = {"platform": "淘宝天猫1688", "region": "中国", "language": "中文"}
PLAN = {"白底": 1, "场景": 1, "卖点": 1}


def to_png(path: str, side: int = 1024) -> bytes:
    img = Image.open(path).convert("RGB")
    s = max(img.size)
    cv = Image.new("RGB", (s, s), (255, 255, 255))
    cv.paste(img, ((s - img.width) // 2, (s - img.height) // 2))
    b = io.BytesIO()
    cv.resize((side, side)).save(b, format="PNG")
    return b.getvalue()


async def sse_collect(c, job, tok):  # noqa: ANN001
    """收 (event, payload) 对，直到 task_completed/failed。"""
    out, ev = [], None
    async with c.stream("GET", f"/listing/{job}/events", params={"access_token": tok}) as s:
        async for line in s.aiter_lines():
            if line.startswith("event:"):
                ev = line.split(":", 1)[1].strip()
            elif line.startswith("data:") and ev:
                try:
                    payload = json.loads(line.split(":", 1)[1].strip() or "{}")
                except json.JSONDecodeError:
                    payload = {}
                out.append((ev, payload))
                if ev in ("task_completed", "task_failed"):
                    break
    return out


async def run_job(c, H, tok, label, src, body_extra):  # noqa: ANN001
    uid = (await c.post("/uploads", headers=H, files={"file": ("p.png", to_png(src), "image/png")})).json()["id"]
    body = {"upload_ids": [uid], "prompt": "电商主图：产品主体清晰、背景干净得体、质感真实突出",
            "ratio": "1:1", "category": "FOOD", "modifiers": MODS, **body_extra}
    t0 = time.perf_counter()
    job = (await c.post("/listing/generate", headers=H, json=body)).json()["job_id"]
    events = await sse_collect(c, job, tok)
    dt = int(time.perf_counter() - t0)
    d = (await c.get(f"/listing/jobs/{job}", headers=H)).json()
    return job, dt, events, d


def check(label, ok, extra=""):  # noqa: ANN001
    print(f"  {'PASS' if ok else 'FAIL'}  {label}{('  ' + extra) if extra else ''}")
    return bool(ok)


def cost_ok(d, k):  # noqa: ANN001
    """provider 价无关：total_cost>0 且 == Σ成功张 cost 且成功张数=k（qa 占位 1.19/prod 0.40 都过）。"""
    from decimal import Decimal
    imgs = [i for i in d.get("images", []) if i.get("status") == "成功"]
    tot = Decimal(str(d.get("total_cost", "0")))
    s = sum((Decimal(str(i.get("cost", "0"))) for i in imgs), Decimal("0"))
    return tot > 0 and tot == s and len(imgs) == k


async def dl(url, fname):  # noqa: ANN001
    async with httpx.AsyncClient(trust_env=False, timeout=60.0) as d:
        r = await d.get(url)
        if r.status_code == 200:
            (OUT / fname).write_bytes(r.content)
            return fname
    return ""


async def main() -> None:
    if not BASE:
        raise SystemExit("✋ QA_BASE 未设置。")
    OUT.mkdir(exist_ok=True)
    print(f"== 套图真出图回归 (0e9ee9d) == BASE={BASE}（7 张 ¥2.80）")
    npass, ntotal = 0, 0

    def tally(ok):  # noqa: ANN001
        nonlocal npass, ntotal
        ntotal += 1
        npass += ok

    async with httpx.AsyncClient(base_url=BASE, trust_env=False, timeout=900.0) as c:
        r = await c.post("/auth/register", json={"email": U[0], "password": U[1], "name": U[2]})
        if r.status_code != 200:
            r = await c.post("/auth/login", json={"email": U[0], "password": U[1]})
        tok = r.json()["jwt"]
        H = {"Authorization": f"Bearer {tok}"}

        # ① 花生 plan 1/1/1 + overlay 2 条
        job, dt, evs, d = await run_job(c, H, tok, "花生", PEANUT,
                                        {"plan": PLAN, "overlay_texts": ["高山七彩花生", "原生态种植"]})
        gen = [(e, p) for e, p in evs if e == "image_generated"]
        types = sorted(p.get("image_type", "?") for _, p in gen)
        imgs = d.get("images", [])
        dtypes = sorted(i.get("image_type") or "?" for i in imgs)
        print(f"\n[① 花生 plan+overlay] job={job} {dt}s status={d.get('status')} cost={d.get('total_cost')}")
        tally(check("SSE image_generated ×3 各带 image_type", types == ["卖点", "场景", "白底"], f"got {types}"))
        tally(check("详情 images[].image_type 分布=1/1/1", dtypes == ["卖点", "场景", "白底"], f"got {dtypes}"))
        tally(check("无 image_failed", not any(e == "image_failed" for e, _ in evs)))
        tally(check("cost=Σ成功张 reconcile(>0)", cost_ok(d, 3), f"total={d.get('total_cost')}"))
        for i in imgs:
            t = i.get("image_type")
            await dl(i["url"], f"花生-{t}{'-有字' if t == '卖点' else ''}.png")

        # ② 润喉糖 plan 1/1/1 无 overlay
        job, dt, evs, d = await run_job(c, H, tok, "润喉糖", LOZENGE, {"plan": PLAN})
        gen = [(e, p) for e, p in evs if e == "image_generated"]
        types = sorted(p.get("image_type", "?") for _, p in gen)
        imgs = d.get("images", [])
        print(f"\n[② 润喉糖 plan 无字] job={job} {dt}s status={d.get('status')} cost={d.get('total_cost')}")
        tally(check("SSE 标签齐 3 型", types == ["卖点", "场景", "白底"], f"got {types}"))
        tally(check("cost=Σ成功张 reconcile(>0)", cost_ok(d, 3), f"total={d.get('total_cost')}"))
        for i in imgs:
            t = i.get("image_type")
            await dl(i["url"], f"润喉糖-{t}{'-无字' if t == '卖点' else ''}.png")

        # ③ 花生 n=1 单图流零破坏
        job, dt, evs, d = await run_job(c, H, tok, "花生n1", PEANUT, {"n": 1})
        imgs = d.get("images", [])
        print(f"\n[③ 花生 n=1 单图流] job={job} {dt}s status={d.get('status')} cost={d.get('total_cost')}")
        tally(check("完成且 1 张", d.get("status") == "完成" and len(imgs) == 1))
        tally(check("image_type 为空（单图流无图型）", imgs and imgs[0].get("image_type") in (None, "")))
        tally(check("cost=单张 reconcile(>0)", cost_ok(d, 1), f"total={d.get('total_cost')}"))
        if imgs:
            await dl(imgs[0]["url"], "花生-n1单图流.png")

    print(f"\n==== 套图真出图回归：{npass}/{ntotal} ====  落盘 → {OUT}（QA 逐张视觉核）")


asyncio.run(main())