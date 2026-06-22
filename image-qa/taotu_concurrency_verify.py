"""套图并发 429 修复验证(ISSUE-0047)——dev 降并发+jitter fix 落 qa 后跑。

bug:apikey 轮换后新 key 并发档低,套图 5 路并发(Semaphore)打满中转站限额→429→部分图
失败→「套图只出 1 张」(真实用户#1)。间歇性(429 看 timing)——故**多遍压并发**验,绝不一遍绿就放。
每遍套图(大 plan 最大化并发压力)断言:
  ① status=完成 ② 成功张数==请求总数(出全套、不缺张) ③ 无 IMAGE_FAILED(无 429 误失败)
  ④ cost 价无关核(total>0 且 ==Σ成功张、张数==请求总数)
连跑 REPEAT 遍,聚合「全出遍数 / 出现缺张或失败的遍数」。任一遍缺张/失败=fix 未稳、SystemExit。
用法：QA_BASE=http://localhost:8444 [PLAN='白底:2,场景:4,卖点:4'] [REPEAT=3] \
      uv run python ../image-qa/taotu_concurrency_verify.py
"""

import asyncio
import io
import os
import time
from decimal import Decimal

import httpx
from PIL import Image

BASE = (os.environ.get("QA_BASE") or os.environ.get("PROD_BASE") or "").rstrip("/")
PREFIX = os.environ.get("API_PREFIX", "").rstrip("/")
REPEAT = int(os.environ.get("REPEAT", "3"))
PLAN = {k: int(v) for k, v in (p.split(":") for p in os.environ.get("PLAN", "白底:2,场景:4,卖点:4").split(","))}
TOTAL = sum(PLAN.values())
SRC = "/Users/Zhuanz/CLAUDE/image-gen/image-qa/通用块多产品/通用块-花生.png"
U = (f"qa-conc-{int(time.time())}@example.com", "qa-conc-123", "QA并发验证")
MODS = {"platform": "淘宝天猫1688", "region": "中国", "language": "中文"}


def to_png(path: str) -> bytes:
    img = Image.open(path).convert("RGB")
    s = max(img.size)
    cv = Image.new("RGB", (s, s), (255, 255, 255))
    cv.paste(img, ((s - img.width) // 2, (s - img.height) // 2))
    b = io.BytesIO()
    cv.resize((1024, 1024)).save(b, format="PNG")
    return b.getvalue()


async def wait_job(c, H, tok, job):  # noqa: ANN001
    evs = []
    try:
        async with c.stream("GET", f"{PREFIX}/listing/{job}/events", params={"access_token": tok}) as s:
            ev = None
            async for line in s.aiter_lines():
                if line.startswith("event:"):
                    ev = line.split(":", 1)[1].strip()
                    evs.append(ev)
                    if ev in ("task_completed", "task_failed"):
                        break
    except httpx.RemoteProtocolError:
        evs.append("__sse_dropped__")
    for _ in range(300):
        d = (await c.get(f"{PREFIX}/listing/jobs/{job}", headers=H)).json()
        if d.get("status") in ("完成", "失败"):
            return d, evs
        await asyncio.sleep(3)
    return (await c.get(f"{PREFIX}/listing/jobs/{job}", headers=H)).json(), evs


async def main() -> None:
    if not BASE:
        raise SystemExit("✋ 未设 QA_BASE/PROD_BASE。")
    print(f"== 套图并发 429 修复验证(ISSUE-0047) == BASE={BASE}{PREFIX or ''}")
    print(f"   plan={PLAN} 总数={TOTAL} 连跑 REPEAT={REPEAT} 遍(压并发，间歇 429 多遍验)")
    full = 0
    async with httpx.AsyncClient(base_url=BASE, trust_env=False, verify=False, timeout=1200.0) as c:
        r = await c.post(f"{PREFIX}/auth/register", json={"email": U[0], "password": U[1], "name": U[2]})
        if r.status_code != 200:
            r = await c.post(f"{PREFIX}/auth/login", json={"email": U[0], "password": U[1]})
        tok = r.json()["jwt"]
        H = {"Authorization": f"Bearer {tok}"}
        uid = (await c.post(f"{PREFIX}/uploads", headers=H, files={"file": ("p.png", to_png(SRC), "image/png")})).json()["id"]
        body = {"upload_ids": [uid], "prompt": "电商主图：产品主体清晰、背景干净得体、质感真实突出",
                "ratio": "1:1", "category": "FOOD", "modifiers": MODS, "plan": PLAN}
        for i in range(1, REPEAT + 1):
            t0 = time.perf_counter()
            job = (await c.post(f"{PREFIX}/listing/generate", headers=H, json=body)).json()["job_id"]
            d, evs = await wait_job(c, H, tok, job)
            dt = int(time.perf_counter() - t0)
            imgs = [im for im in d.get("images", []) if im.get("status") == "成功"]
            tot = Decimal(str(d.get("total_cost", "0")))
            sum_ok = sum((Decimal(str(im.get("cost", "0"))) for im in imgs), Decimal("0"))
            img_failed = evs.count("image_failed") + sum(1 for im in d.get("images", []) if im.get("status") not in ("成功",))
            ok = (d.get("status") == "完成" and len(imgs) == TOTAL and img_failed == 0
                  and tot > 0 and tot == sum_ok)
            full += ok
            flag = "" if ok else "  🔴 缺张/失败(429 未修好?)"
            print(f"  [{i}/{REPEAT}] {'PASS' if ok else 'FAIL'} job={job[:12]} {dt}s status={d.get('status')} "
                  f"成功={len(imgs)}/{TOTAL} 失败={img_failed} cost=¥{tot}{flag}")
    print(f"\n==== 套图并发验证:{full}/{REPEAT} 遍全出 ====（{REPEAT}遍 ×{TOTAL}张压并发；全绿=降并发后稳定不再 429 误失败）")
    if full != REPEAT:
        raise SystemExit("🔴 有遍次缺张/失败——降并发 fix 未稳,STOP 报 coordinator/dev,别放行部署。")


asyncio.run(main())
