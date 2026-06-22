"""用户指定:admin 账号 prod 测爆款复刻几遍(两档×两产品)。

登录 admin(creds 从 env、不硬编码不入库)→ 4 遍复刻(ratio 3:4 配竖版爆款大图)：
  ① 花生 × 花生爆款大图(同款) × 参考风格   ② 花生 × 同 × 高度复刻
  ③ 润喉糖 × 花生爆款大图(跨产品测泄漏) × 参考风格   ④ 润喉糖 × 同 × 高度复刻
参考图统一=共评样张/淘宝天猫1688-3x4-中文.png(花生真爆款精修大图)。
③④跨产品=测复刻头号命门:产物只迁移风格、绝不泄漏参考图的花生。
SSE 断连降级轮询。成品落 image-qa/admin复刻test/、打印路径 + job/状态/cost/clone_mode。
用法：PROD_BASE=https://203.0.113.10 API_PREFIX=/api ADMIN_EMAIL=... ADMIN_PASSWORD=... \
      uv run python ../image-qa/admin_clone_test.py
"""

import asyncio
import io
import os
import time
from decimal import Decimal
from pathlib import Path

import httpx
from PIL import Image

BASE = (os.environ.get("PROD_BASE") or os.environ.get("QA_BASE") or "").rstrip("/")
PREFIX = os.environ.get("API_PREFIX", "").rstrip("/")
EMAIL = os.environ.get("ADMIN_EMAIL", "")
PASSWORD = os.environ.get("ADMIN_PASSWORD", "")
OUT = Path("/Users/Zhuanz/CLAUDE/image-gen/image-qa/admin复刻test")
MODS = {"platform": "淘宝天猫1688", "region": "中国", "language": "中文"}
PEANUT = "/Users/Zhuanz/CLAUDE/image-gen/image-qa/通用块多产品/通用块-花生.png"
LOZENGE = "/Users/Zhuanz/CLAUDE/image-gen/image-qa/套图回归/润喉糖-白底.png"
REF = "/Users/Zhuanz/CLAUDE/image-gen/image-qa/爆款参考/云南七彩花生-爆款图.jpg"  # 用户提供·云南七彩花生真实爆款大图
# (label, 产品图, 档位)；参考图统一 REF（用户提供的花生爆款图），花生品类两档
RUNS = [
    ("花生×参考风格", PEANUT, "参考风格"),
    ("花生×高度复刻", PEANUT, "高度复刻"),
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
    if not (BASE and EMAIL and PASSWORD):
        raise SystemExit("✋ 需 PROD_BASE/ADMIN_EMAIL/ADMIN_PASSWORD。")
    OUT.mkdir(exist_ok=True)
    print(f"== admin 爆款复刻实测 == BASE={BASE}{PREFIX or ''} 账号={EMAIL}")
    print(f"   参考爆款大图={Path(REF).name}（用户提供·云南七彩花生）  ratio=1:1")
    summary = []
    async with httpx.AsyncClient(base_url=BASE, trust_env=False, verify=False, timeout=900.0) as c:
        r = await c.post(f"{PREFIX}/auth/login", json={"email": EMAIL, "password": PASSWORD})
        if r.status_code != 200:
            raise SystemExit(f"🔴 登录失败 {r.status_code}: {r.text[:200]}")
        tok = r.json()["jwt"]
        H = {"Authorization": f"Bearer {tok}"}
        print(f"  登录成功 role={r.json().get('role')} name={r.json().get('name')}")
        rid = await upload(c, H, REF)  # 参考图统一上传一次

        for label, prod, mode in RUNS:
            pid = await upload(c, H, prod)
            body = {"product_upload_ids": [pid], "reference_upload_ids": [rid], "clone_mode": mode,
                    "prompt": "电商主图：产品主体清晰、质感真实突出", "ratio": "1:1",
                    "category": "FOOD", "modifiers": MODS}
            t0 = time.perf_counter()
            job = (await c.post(f"{PREFIX}/listing/clone", headers=H, json=body)).json()["job_id"]
            d = await wait_job(c, H, tok, job)
            dt = int(time.perf_counter() - t0)
            imgs = [i for i in d.get("images", []) if i.get("status") == "成功"]
            tot = Decimal(str(d.get("total_cost", "0")))
            path = ""
            if imgs:
                async with httpx.AsyncClient(trust_env=False, verify=False, timeout=60.0) as dl:
                    resp = await dl.get(imgs[0]["url"])
                    if resp.status_code == 200:
                        path = str(OUT / f"{label}.png")
                        Path(path).write_bytes(resp.content)
            print(f"\n[{label}] job={job} {dt}s status={d.get('status')} cost={tot} clone_mode={d.get('clone_mode')} roles={d.get('input_roles')}")
            print(f"   成品 → {path or '（无：出图失败）'}")
            summary.append((label, job, d.get("status"), tot, path))

    print("\n==== admin 爆款复刻实测汇总 ====")
    for label, job, st, tot, path in summary:
        print(f"  · {label}: {st} / cost=¥{tot} / {path}")


asyncio.run(main())
