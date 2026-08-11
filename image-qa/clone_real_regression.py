"""爆款复刻真出图回归（骨架 RC-01~05 三命门视觉核，dev d8e74bb 契约）。

测试数据策略=**跨产品模板**最大化命门①检出：产品图与参考模板用不同产品，
产物绝不该出现模板产品（命门①竞品泄漏）。4 单 2产品×2档（¥1.60）：
  ① 花生产品 × 润喉糖模板 × 参考风格   ② 花生产品 × 润喉糖模板 × 高度复刻
  ③ 润喉糖产品 × 花生模板 × 参考风格   ④ 润喉糖产品 × 花生模板 × 高度复刻
API 断言：job 完成 / 1 张 / image_type=null（复刻张，dev #562）/ clone_mode 回显 /
input_roles 双角色回显 / cost reconcile。落盘 → image-qa/复刻回归/ 逐张视觉核三命门：
  ①竞品泄漏（产物无模板产品/品牌）②产品被带歪（用户产品保真 verbatim）③文案错位（无糊文案/未给文案留白不自编）。
⚠️ dev /clone + ops 重建 qa 后跑。用法：QA_BASE=http://localhost:8444 uv run python ../image-qa/clone_real_regression.py
"""

import asyncio
import io
import os
import time
from decimal import Decimal
from pathlib import Path

import httpx

from qa_auth import login_verified_account
from PIL import Image

BASE = os.environ.get("QA_BASE", "").rstrip("/")
EP = "/listing/clone"
OUT = Path("/Users/Zhuanz/CLAUDE/image-gen/image-qa/复刻回归")
PEANUT = "/Users/Zhuanz/CLAUDE/image-gen/image-qa/通用块多产品/通用块-花生.png"
LOZENGE = "/Users/Zhuanz/CLAUDE/image-gen/image-qa/套图回归/润喉糖-白底.png"
MODS = {"platform": "淘宝天猫1688", "region": "中国", "language": "中文"}
# (label, 产品图, 模板图, 档位)
RUNS = [
    ("花生产品×润喉糖模板·参考风格", PEANUT, LOZENGE, "参考风格"),
    ("花生产品×润喉糖模板·高度复刻", PEANUT, LOZENGE, "高度复刻"),
    ("润喉糖产品×花生模板·参考风格", LOZENGE, PEANUT, "参考风格"),
    ("润喉糖产品×花生模板·高度复刻", LOZENGE, PEANUT, "高度复刻"),
]
RUNS = RUNS[int(os.environ.get("CLONE_START", "0")):]  # CLONE_START=2 只重跑反向 ③④


def to_png(path: str) -> bytes:
    img = Image.open(path).convert("RGB")
    s = max(img.size)
    cv = Image.new("RGB", (s, s), (255, 255, 255))
    cv.paste(img, ((s - img.width) // 2, (s - img.height) // 2))
    b = io.BytesIO()
    cv.resize((1024, 1024)).save(b, format="PNG")
    return b.getvalue()


def check(label, ok, extra=""):  # noqa: ANN001
    print(f"  {'PASS' if ok else 'FAIL'}  {label}{('  ' + extra) if extra else ''}")
    return bool(ok)


async def upload(c, H, path):  # noqa: ANN001
    return (await c.post("/uploads", headers=H, files={"file": ("p.png", to_png(path), "image/png")})).json()["id"]


async def main() -> None:
    if not BASE:
        raise SystemExit("✋ QA_BASE 未设置。")
    async with httpx.AsyncClient(base_url=BASE, trust_env=False, timeout=900.0) as c:
        OUT.mkdir(exist_ok=True)
        print(f"== 爆款复刻真出图回归 (d8e74bb) == BASE={BASE}（4 单 ¥1.60）")
        session = await login_verified_account(c)
        tok = session.jwt
        H = {"Authorization": f"Bearer {tok}"}
        # 端点探测不走 /openapi.json（docs 默认关后 404，dev #612）：空 body POST → 路由缺=404
        if (await c.post(EP, headers=H, json={})).status_code == 404:
            raise SystemExit(f"⏳ {EP} 尚未上线（ops 未重建 qa 含 d8e74bb？）")
        npass, ntotal = 0, 0
        for label, prod, ref, mode in RUNS:
            pid = await upload(c, H, prod)
            rid = await upload(c, H, ref)
            bdy = {"product_upload_ids": [pid], "reference_upload_ids": [rid], "clone_mode": mode,
                   "prompt": "电商主图：产品主体清晰、质感真实", "ratio": "1:1", "category": "FOOD", "modifiers": MODS}
            t0 = time.perf_counter()
            job = (await c.post(EP, headers=H, json=bdy)).json()["job_id"]
            evs = []
            try:
                async with c.stream("GET", f"/listing/{job}/events", params={"access_token": tok}) as s:
                    ev = None
                    async for line in s.aiter_lines():
                        if line.startswith("event:"):
                            ev = line.split(":", 1)[1].strip()
                        elif line.startswith("data:") and ev:
                            evs.append((ev, line.split(":", 1)[1].strip()))
                            if ev in ("task_completed", "task_failed"):
                                break
            except httpx.RemoteProtocolError:
                # SSE 连接 I/O 瞬时断连 → 降级轮询 job 状态（CLAUDE.md 允许 I/O 降级）
                print(f"  [SSE 断连，降级轮询 job={job}]")
                for _ in range(120):
                    jd = (await c.get(f"/listing/jobs/{job}", headers=H)).json()
                    if jd.get("status") in ("完成", "失败"):
                        break
                    await asyncio.sleep(3)
            dt = int(time.perf_counter() - t0)
            d = (await c.get(f"/listing/jobs/{job}", headers=H)).json()
            imgs = [i for i in d.get("images", []) if i.get("status") == "成功"]
            tot = Decimal(str(d.get("total_cost", "0")))
            cost_ok = tot > 0 and tot == sum((Decimal(str(i.get("cost", "0"))) for i in imgs), Decimal("0"))
            print(f"\n[{label}] job={job} {dt}s status={d.get('status')} cost={tot} clone_mode={d.get('clone_mode')} roles={d.get('input_roles')}")
            for nm, ok in [
                ("完成且 1 张", d.get("status") == "完成" and len(imgs) == 1),
                ("复刻张 image_type=null", bool(imgs) and imgs[0].get("image_type") in (None, "")),
                ("clone_mode 回显=请求档", d.get("clone_mode") == mode),
                ("input_roles 双角色回显", bool(d.get("input_roles")) and "product" in str(d.get("input_roles")) and "reference" in str(d.get("input_roles"))),
                ("cost reconcile(>0)", cost_ok),
            ]:
                ntotal += 1
                npass += check(nm, ok)
            if imgs:
                async with httpx.AsyncClient(trust_env=False, timeout=60.0) as dl:
                    resp = await dl.get(imgs[0]["url"])
                    if resp.status_code == 200:
                        (OUT / f"{label}.png").write_bytes(resp.content)
        print(f"\n==== 复刻真出图 API：{npass}/{ntotal} ====  落盘 → {OUT}")
        print("QA 逐张视觉核三命门：①产物无模板产品/品牌(竞品泄漏) ②用户产品保真不带歪 ③无糊文案/未给文案留白不自编")


asyncio.run(main())
