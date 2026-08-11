"""完全复刻验收(ISSUE/spec 2026-06-15-clone-full-replicate)——admin 2 测试。

dev+prompt 完工后跑。完全复刻=三贴一隔+保真:风格完全复制 + 文字样式复刻 +
文案=用户 overlay verbatim(不填不上字) + 参考图文案零泄漏 + 产品保真。
2 测试(spec §六):
  A. clone_mode=完全复刻 + overlay=['清脆爽口','甘香回甜'] → 风格贴+字按参考样式+内容=我的overlay+无竞品文案泄漏+保真
  B. clone_mode=完全复刻 + 无 overlay → 纯风格复刻+不上字(不自编)+保真+无泄漏
产品=花生、参考=用户提供云南七彩花生爆款图、ratio 1:1、admin、prod。
落 image-qa/admin完全复刻test/、打印路径+job/cost/clone_mode。视觉核 QA 逐张看(5 条验收)。
⚠️ dev 未上线完全复刻前跑会 400(未知档位)→脚本探测优雅退出。
用法：PROD_BASE=https://203.0.113.10 API_PREFIX=/api ADMIN_EMAIL=... ADMIN_PASSWORD=... \
      uv run python ../image-qa/admin_full_clone_test.py
"""

import asyncio
import io
import os
import time
from decimal import Decimal
from pathlib import Path

import httpx

from qa_auth import AccountSlot, login_verified_account
from PIL import Image

BASE = (os.environ.get("PROD_BASE") or os.environ.get("QA_BASE") or "").rstrip("/")
PREFIX = os.environ.get("API_PREFIX", "").rstrip("/")
OUT = Path("/Users/Zhuanz/CLAUDE/image-gen/image-qa/admin完全复刻test")
PRODUCT = "/Users/Zhuanz/CLAUDE/image-gen/image-qa/通用块多产品/通用块-花生.png"
REF = "/Users/Zhuanz/CLAUDE/image-gen/image-qa/爆款参考/云南七彩花生-爆款图.jpg"
MODS = {"platform": "淘宝天猫1688", "region": "中国", "language": "中文"}
MODE = "完全复刻"
# (label, overlay_texts)
TESTS = [
    ("A-带文案", ["清脆爽口", "甘香回甜"]),
    ("B-无文案", []),
]


def to_png(path: str) -> bytes:
    img = Image.open(path).convert("RGB")
    s = max(img.size)
    cv = Image.new("RGB", (s, s), (255, 255, 255))
    cv.paste(img, ((s - img.width) // 2, (s - img.height) // 2))
    b = io.BytesIO()
    cv.resize((1024, 1024)).save(b, format="PNG")
    return b.getvalue()


async def upload(c, H, path):  # noqa: ANN001
    return (await c.post(f"{PREFIX}/uploads", headers=H, files={"file": ("p.png", to_png(path), "image/png")})).json()["id"]


async def wait_job(c, H, tok, job):  # noqa: ANN001
    try:
        async with c.stream("GET", f"{PREFIX}/listing/{job}/events", params={"access_token": tok}) as s:
            ev = None
            async for line in s.aiter_lines():
                if line.startswith("event:"):
                    ev = line.split(":", 1)[1].strip()
                    if ev in ("task_completed", "task_failed"):
                        break
    except httpx.RemoteProtocolError:
        print(f"  [SSE 断连→降级轮询 job={job}]")
    for _ in range(240):
        d = (await c.get(f"{PREFIX}/listing/jobs/{job}", headers=H)).json()
        if d.get("status") in ("完成", "失败"):
            return d
        await asyncio.sleep(3)
    return (await c.get(f"{PREFIX}/listing/jobs/{job}", headers=H)).json()


async def main() -> None:
    if not BASE:
        raise SystemExit("✋ 需 PROD_BASE/ADMIN_EMAIL/ADMIN_PASSWORD。")
    OUT.mkdir(exist_ok=True)
    print(f"== admin 完全复刻验收 == BASE={BASE}{PREFIX or ''} 账号=runtime ADMIN_EMAIL")
    print(f"   产品=花生  参考={Path(REF).name}  clone_mode={MODE}  ratio=1:1")
    summary = []
    async with httpx.AsyncClient(base_url=BASE, trust_env=False, verify=False, timeout=900.0) as c:
        session = await login_verified_account(c, prefix=PREFIX, slot=AccountSlot.ADMIN)
        tok = session.jwt
        H = {"Authorization": f"Bearer {tok}"}
        print(f"  Login succeeded for {session.email}")
        pid = await upload(c, H, PRODUCT)
        rid = await upload(c, H, REF)

        for label, overlay in TESTS:
            body = {"product_upload_ids": [pid], "reference_upload_ids": [rid], "clone_mode": MODE,
                    "prompt": "电商主图：产品主体清晰、质感真实突出", "ratio": "1:1",
                    "category": "FOOD", "modifiers": MODS}
            if overlay:
                body["overlay_texts"] = overlay
            t0 = time.perf_counter()
            resp = await c.post(f"{PREFIX}/listing/clone", headers=H, json=body)
            if resp.status_code != 200:
                print(f"\n[{label}] 🔴 clone 提交 {resp.status_code}: {resp.text[:160]}")
                if resp.status_code in (400, 422):
                    print("   ↑ 完全复刻档/overlay_texts 可能尚未上线(dev 未完工?)——预写脚本待 dev 后跑。")
                summary.append((label, "-", resp.status_code, "-", "-", ""))
                continue
            job = resp.json()["job_id"]
            d = await wait_job(c, H, tok, job)
            dt = int(time.perf_counter() - t0)
            imgs = [i for i in d.get("images", []) if i.get("status") == "成功"]
            tot = Decimal(str(d.get("total_cost", "0")))
            path = ""
            if imgs:
                async with httpx.AsyncClient(trust_env=False, verify=False, timeout=60.0) as dl:
                    rr = await dl.get(imgs[0]["url"])
                    if rr.status_code == 200:
                        path = str(OUT / f"完全复刻-{label}.png")
                        Path(path).write_bytes(rr.content)
            print(f"\n[{label}] job={job} {dt}s status={d.get('status')} cost=¥{tot} clone_mode={d.get('clone_mode')} overlay={overlay or '(无)'}")
            print(f"   成品 → {path or '（无：出图失败）'}")
            summary.append((label, job, d.get("status"), tot, d.get("clone_mode"), path))

    print("\n==== admin 完全复刻验收汇总（QA 逐张视觉核 5 条:风格贴/字样贴/竞品文案零泄漏/用户文案verbatim/无糊字）====")
    for label, job, st, tot, cm, path in summary:
        print(f"  · {label}: {st} / cost=¥{tot} / clone_mode={cm} / {path}")


asyncio.run(main())
