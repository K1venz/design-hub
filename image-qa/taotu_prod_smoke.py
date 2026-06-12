"""套图 prod 终验 — ISSUE-0045 over-deliver 真实流量复测（部署后，coordinator #748 派）。

背景（读 05cc6b6 _parse:167-195 实证）：二修 over-deliver(len>n)→`data[:n]` **静默截断 +
按 n 计费 + 不失败**（第 182 行，无任何 log/warning）；under-deliver(len<n) 才抛
ProviderError「出图数量不足」。⇒ 黑盒侧（API/DB/日志）一个被正确处理的 over-deliver 与
正常 n=1→1 **不可区分**（设计使然，非没跑到）。故 prod 终验**结构上只能验**：
  ① 无回归：套图不再误判失败（=一修矫枉过正消失，status 恒「完成」、零误判 IMAGE_FAILED）
  ② 无资损：cost == 请求张数 × 单价，与中转站返回 len 解耦（原 0045 资损消失）
用户刚在 prod 撞到 over-deliver ⇒ 中转站当前在多返 ⇒ 本次 JOBS×5 次 n=1 调用极可能
**真实经历 over-deliver**，若全 clean = 二修在真实 over-deliver 下工作的强证据（只是无法
逐调用指认哪次被截断——静默）。撞不到则如实报「无回归 + over 分支靠 spec 单测兜底」。

每单跑默认套图(1/2/2=5)，验：完成 + 恰 5 张 + 分布 1/2/2 + 无失败图 +
cost==5×UNIT（资损核·与返回 len 解耦）+ cost==Σ成功张（内部自洽）+ 落 prod 桶。
bounded：JOBS 固定（默认 3 = 15 次 n=1 调用、≈¥6），绝不为撞偶发无限跑。
用法：PROD_BASE=https://14.103.51.191 API_PREFIX=/api JOBS=3 uv run python ../image-qa/taotu_prod_smoke.py
     （直连绕 nginx：PROD_BASE=http://localhost:8446 API_PREFIX= ）
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
PREFIX = os.environ.get("API_PREFIX", "").rstrip("/")  # 公网=/api、8446 直连=空
JOBS = int(os.environ.get("JOBS", "3"))
UNIT = Decimal(os.environ.get("UNIT", "0.40"))  # prod 单张价
SRC = "/Users/Zhuanz/CLAUDE/image-gen/image-qa/通用块多产品/通用块-花生.png"
OUT = Path("/Users/Zhuanz/CLAUDE/image-gen/image-qa/套图prod_smoke")
U = (f"qa-taotu-prod-{int(time.time())}@example.com", "qa-taotu-prod-123", "QA套图prod终验")
PLAN = {"白底": 1, "场景": 2, "卖点": 2}
R = sum(PLAN.values())  # 请求张数=5
DIST_EXP = sorted(["白底"] * 1 + ["场景"] * 2 + ["卖点"] * 2)  # ['卖点','卖点','场景','场景','白底']


def to_png(p):  # noqa: ANN001
    img = Image.open(p).convert("RGB")
    s = max(img.size)
    cv = Image.new("RGB", (s, s), (255, 255, 255))
    cv.paste(img, ((s - img.width) // 2, (s - img.height) // 2))
    b = io.BytesIO()
    cv.resize((1024, 1024)).save(b, format="PNG")
    return b.getvalue()


async def wait_job(c, H, tok, job):  # noqa: ANN001
    """SSE 收事件，断连降级轮询；权威以 job detail 为准。返回 (events, detail)。"""
    events = []
    try:
        async with c.stream("GET", f"{PREFIX}/listing/{job}/events", params={"access_token": tok}) as s:
            ev = None
            async for line in s.aiter_lines():
                if line.startswith("event:"):
                    ev = line.split(":", 1)[1].strip()
                elif line.startswith("data:") and ev:
                    events.append(ev)
                    if ev in ("task_completed", "task_failed"):
                        break
    except httpx.RemoteProtocolError:
        events.append("__sse_dropped__")
    for _ in range(200):
        d = (await c.get(f"{PREFIX}/listing/jobs/{job}", headers=H)).json()
        if d.get("status") in ("完成", "失败"):
            return events, d
        await asyncio.sleep(3)
    return events, (await c.get(f"{PREFIX}/listing/jobs/{job}", headers=H)).json()


async def run_one(c, H, tok, uid, idx):  # noqa: ANN001
    body = {"upload_ids": [uid], "prompt": "电商主图：产品主体清晰、背景干净得体、质感真实突出",
            "ratio": "1:1", "category": "FOOD",
            "modifiers": {"platform": "淘宝天猫1688", "region": "中国", "language": "中文"}, "plan": PLAN}
    t0 = time.perf_counter()
    job = (await c.post(f"{PREFIX}/listing/generate", headers=H, json=body)).json()["job_id"]
    events, d = await wait_job(c, H, tok, job)
    dt = int(time.perf_counter() - t0)

    all_imgs = d.get("images", [])
    imgs = [i for i in all_imgs if i.get("status") == "成功"]
    dist = sorted(i.get("image_type") or "?" for i in imgs)
    tot = Decimal(str(d.get("total_cost", "0")))
    sum_img = sum((Decimal(str(i.get("cost", "0"))) for i in imgs), Decimal("0"))
    prod_bucket = bool(imgs) and all("bucket-design-hub-generate" in i["url"] and "qa-generate" not in i["url"] for i in imgs)

    checks = [
        ("完成（非误判失败=矫枉过正消失）", d.get("status") == "完成"),
        (f"恰 {R} 张成功、无失败行", len(imgs) == R and len(all_imgs) == R),
        ("分布 白底1/场景2/卖点2", dist == DIST_EXP),
        ("无 IMAGE_FAILED 事件", "image_failed" not in events),
        (f"cost==请求{R}×{UNIT}={R * UNIT}（资损核·解耦返回len）", tot == R * UNIT),
        ("cost==Σ成功张（内部自洽）", tot > 0 and tot == sum_img),
        ("落 prod 桶（非 qa）", prod_bucket),
    ]
    job_ok = all(ok for _, ok in checks)
    print(f"\n[单 {idx}] job={job[:12]} {dt}s status={d.get('status')} cost={tot} 成功={len(imgs)}/{len(all_imgs)} dist={dist}")
    for name, ok in checks:
        print(f"    {'PASS' if ok else '🔴 FAIL'}  {name}")
    if d.get("status") == "失败":
        print(f"    ⚠ 失败 reason={d.get('error') or d.get('failure_reason') or '?'}（若=张数不符=二修没修好；真 under-deliver=中转站没出图）")

    for i in imgs:
        t = i.get("image_type")
        async with httpx.AsyncClient(trust_env=False, verify=False, timeout=60.0) as dl:
            resp = await dl.get(i["url"])
            if resp.status_code == 200:
                (OUT / f"prod-j{idx}-{t}-{i['url'].split('/')[-1][:8]}.png").write_bytes(resp.content)
    return job_ok, tot, d.get("status")


async def main():  # noqa: ANN001
    if not BASE:
        raise SystemExit("✋ PROD_BASE 未设置——必须显式指向部署后 prod（公网或隧道）。")
    OUT.mkdir(exist_ok=True)
    print(f"== 套图 prod 终验（ISSUE-0045 over-deliver）== BASE={BASE}{PREFIX or ''} JOBS={JOBS} 每单 {R} 张")
    print(f"   单价 UNIT={UNIT}、预计 {JOBS}×{R}={JOBS * R} 次 n=1 调用、≈¥{JOBS * R * UNIT}")
    print("   ⚠ over-deliver 截断静默（_parse:182 无日志）→ 验 no-regression + no-资损；撞不到如实报。")
    async with httpx.AsyncClient(base_url=BASE, trust_env=False, verify=False, timeout=900.0) as c:
        r = await c.post(f"{PREFIX}/auth/register", json={"email": U[0], "password": U[1], "name": U[2]})
        if r.status_code != 200:
            r = await c.post(f"{PREFIX}/auth/login", json={"email": U[0], "password": U[1]})
        tok = r.json()["jwt"]
        H = {"Authorization": f"Bearer {tok}"}
        uid = (await c.post(f"{PREFIX}/uploads", headers=H, files={"file": ("p.png", to_png(SRC), "image/png")})).json()["id"]

        jobs_pass, fails, total_cost = 0, 0, Decimal("0")
        for idx in range(1, JOBS + 1):
            ok, tot, status = await run_one(c, H, tok, uid, idx)
            jobs_pass += ok
            fails += status == "失败"
            total_cost += tot

    print(f"\n==== 套图 prod 终验：{jobs_pass}/{JOBS} 单全绿 ====")
    print(f"   误判失败单数={fails}（应=0：矫枉过正消失）｜总计费=¥{total_cost}（应=¥{JOBS * R * UNIT}=请求张数×单价：资损消失）")
    print(f"   覆盖 {JOBS * R} 次 n=1 真实调用。over-deliver 若发生=已被二修静默截断吸收（黑盒不可逐次指认）。")
    print(f"   落盘 → {OUT}（QA 逐张视觉核：保真+图型像型）。qa-test 号 {U[0]} → @ops 清 footprint。")


asyncio.run(main())
