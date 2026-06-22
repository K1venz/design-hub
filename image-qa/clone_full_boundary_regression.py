"""完全复刻契约边界回归(spec 2026-06-15 + coordinator #847)——零出图。

覆盖完全复刻新契约的 fail-fast(invalid 请求在出图前被拒、不烧 gpt):
  ① 参考风格 + overlay_texts(非空) → **400**(coordinator #847 定向:显式拒、非静默忽略)
  ② 完全复刻 + overlay 超 2 条 → 拒(4xx,沿卖点图 2 条上限)
  ③ 完全复刻 + overlay 单条超 12 字 → 拒
  ④ 完全复刻 + overlay 含空白条 → 拒
  ⑤ 高度复刻(旧值,已改名完全复刻) → 400 未知档位(若 dev 移除旧值;别名保留则 FAIL 提示)
断言取「是否被拒(4xx)」语义、并打印实际码(400/422 由 dev 实现定、我据此核契约)。
纯 invalid 用例=出图前被拒、零 gpt 成本(合法接受由视觉脚本 admin_full_clone_test 覆盖,不在此重复烧)。
⚠️ dev 上线完全复刻+overlay 前,①②③④可能因"完全复刻未知档/overlay 未加"而提前 400/422——
   脚本打印实际码,我对 spec 核。
用法：QA_BASE=http://localhost:8444 uv run python ../image-qa/clone_full_boundary_regression.py
"""

import asyncio
import io
import os
import time

import httpx
from PIL import Image

BASE = (os.environ.get("QA_BASE") or os.environ.get("PROD_BASE") or "").rstrip("/")
PREFIX = os.environ.get("API_PREFIX", "").rstrip("/")
U = (f"qa-fclone-b-{int(time.time())}@example.com", "qa-fclone-123", "QA完全复刻边界")
PRODUCT = "/Users/Zhuanz/CLAUDE/image-gen/image-qa/通用块多产品/通用块-花生.png"
REF = "/Users/Zhuanz/CLAUDE/image-gen/image-qa/爆款参考/云南七彩花生-爆款图.jpg"
MODS = {"platform": "淘宝天猫1688", "region": "中国", "language": "中文"}

_p = _t = 0


def ck(label, ok, extra=""):  # noqa: ANN001
    global _p, _t
    _t += 1
    _p += bool(ok)
    print(f"  {'PASS' if ok else '🔴 FAIL'}  {label}{('  ' + extra) if extra else ''}")


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


async def main() -> None:
    if not BASE:
        raise SystemExit("✋ 未设 QA_BASE/PROD_BASE。")
    print(f"== 完全复刻契约边界回归 == BASE={BASE}{PREFIX or ''}")
    async with httpx.AsyncClient(base_url=BASE, trust_env=False, verify=False, timeout=120.0) as c:
        r = await c.post(f"{PREFIX}/auth/register", json={"email": U[0], "password": U[1], "name": U[2]})
        if r.status_code != 200:
            r = await c.post(f"{PREFIX}/auth/login", json={"email": U[0], "password": U[1]})
        tok = r.json()["jwt"]
        H = {"Authorization": f"Bearer {tok}"}
        pid = await upload(c, H, PRODUCT)
        rid = await upload(c, H, REF)
        base = {"product_upload_ids": [pid], "reference_upload_ids": [rid],
                "prompt": "电商主图：产品主体清晰", "ratio": "1:1", "category": "FOOD", "modifiers": MODS}

        async def post(extra):  # noqa: ANN001
            return (await c.post(f"{PREFIX}/listing/clone", headers=H, json={**base, **extra})).status_code

        # ① 参考风格 + overlay 非空 → 400(coordinator #847 显式拒)
        sc = await post({"clone_mode": "参考风格", "overlay_texts": ["清脆爽口"]})
        ck("① 参考风格+overlay → 400", sc == 400, f"got {sc}")
        # ② 完全复刻 + overlay 3 条 → 拒(>2)
        sc = await post({"clone_mode": "完全复刻", "overlay_texts": ["清脆爽口", "甘香回甜", "拒绝添加"]})
        ck("② 完全复刻+overlay 3条 → 4xx拒", sc in (400, 422), f"got {sc}")
        # ③ 完全复刻 + 单条 13 字 → 拒(>12)
        sc = await post({"clone_mode": "完全复刻", "overlay_texts": ["一二三四五六七八九十一二三"]})
        ck("③ 完全复刻+13字 → 4xx拒", sc in (400, 422), f"got {sc}")
        # ④ 完全复刻 + 空白条 → 拒
        sc = await post({"clone_mode": "完全复刻", "overlay_texts": ["  "]})
        ck("④ 完全复刻+空白条 → 4xx拒", sc in (400, 422), f"got {sc}")
        # ⑤ 旧值 高度复刻 → 400 未知档位(改名后;别名保留则此条 FAIL=提示别名仍在)
        sc = await post({"clone_mode": "高度复刻"})
        ck("⑤ 旧值 高度复刻 → 400(已改名完全复刻)", sc == 400, f"got {sc}（非400=旧值仍在/别名保留,核 dev 迁移）")

    print(f"\n==== 完全复刻边界:{_p}/{_t} ====（纯 invalid 零出图;实际码见上行,据此对 spec 核 400/422 契约）")


asyncio.run(main())
