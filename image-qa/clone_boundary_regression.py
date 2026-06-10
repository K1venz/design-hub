"""爆款复刻边界/契约回归（零成本，骨架 RC-06~09 + C7 选填）。

⚠️ 预写：按 dev #541/#547/#559 锁定契约（POST /listing/clone、双角色显式双字段、
product==1 / reference 1..2 / clone_mode∈{参考风格,高度复刻} / prompt 选填 / 两类 owns 404）。
**dev /clone 落地后先核 openapi 字段名/路径，再跑。**
GHOST 技法：合法契约 + 幽灵 upload id → 过校验后卡 owns→404；契约非法→400/422。零出图零成本。
用法：QA_BASE=http://localhost:8444 uv run python ../image-qa/clone_boundary_regression.py
"""

import asyncio
import os
import time

import httpx

BASE = os.environ.get("QA_BASE", "").rstrip("/")
EP = "/listing/clone"  # dev (b) 瘦路由；openapi 落地核一遍
U = (f"qa-clone-b-{int(time.time())}@example.com", "qa-clone-123", "QA复刻边界")
G1, G2, G3 = "0000000000000000.png", "1111111111111111.png", "2222222222222222.png"


def body(product=None, reference=None, mode="参考风格", prompt="电商主图：产品主体清晰", overlay=None):  # noqa: ANN001
    b = {"ratio": "1:1", "category": "FOOD",
         "modifiers": {"platform": "淘宝天猫1688", "region": "中国", "language": "中文"}}
    if product is not None:
        b["product_upload_ids"] = product
    if reference is not None:
        b["reference_upload_ids"] = reference
    if mode is not None:
        b["clone_mode"] = mode
    if prompt is not None:
        b["prompt"] = prompt
    if overlay is not None:
        b["overlay_texts"] = overlay
    return b


CASES = [
    ("产品图缺→400", body(product=None, reference=[G2]), {400, 422}),
    ("产品图0张→400", body(product=[], reference=[G2]), {400, 422}),
    ("产品图2张(>1)→400", body(product=[G1, G3], reference=[G2]), {400}),
    ("参考图缺→400", body(product=[G1], reference=None), {400, 422}),
    ("参考图0张→400", body(product=[G1], reference=[]), {400, 422}),
    ("参考图3张(>2)→400", body(product=[G1], reference=[G2, G3, "3333333333333333.png"]), {400}),
    ("clone_mode缺→400", body(product=[G1], reference=[G2], mode=None), {400, 422}),
    ("clone_mode非法→400", body(product=[G1], reference=[G2], mode="超级复刻"), {400, 422}),
    # CloneRequest 无 overlay_texts 字段 → pydantic 忽略 extra（非 400）→ 正常走到 owns 404；功能上「overlay 不进复刻流」满足（无影响）
    ("overlay_texts无此字段·忽略不影响→404", body(product=[G1], reference=[G2], overlay=["促销"]), {404}),
    ("合法·参考风格·prompt给→过契约 owns 404", body(product=[G1], reference=[G2], mode="参考风格"), {404}),
    ("合法·高度复刻·ref2→过契约 owns 404", body(product=[G1], reference=[G2, G3], mode="高度复刻"), {404}),
    ("C7 复刻 prompt 空=合法→过契约 owns 404", body(product=[G1], reference=[G2], prompt=""), {404}),
    ("C7 复刻 prompt 缺=合法→过契约 owns 404", body(product=[G1], reference=[G2], prompt=None), {404}),
]


async def main() -> None:
    if not BASE:
        raise SystemExit("✋ QA_BASE 未设置。")
    print(f"== 爆款复刻边界/契约回归（预写）== BASE={BASE} EP={EP}")
    async with httpx.AsyncClient(base_url=BASE, trust_env=False, timeout=60.0) as c:
        op = await c.get("/openapi.json")
        has_ep = EP in op.text
        print(f"[probe] openapi {op.status_code}  /clone 端点已上={has_ep}")
        if not has_ep:
            raise SystemExit(f"⏳ {EP} 尚未上线（dev 未 wiring）——预写脚本待 dev 完工 + openapi 核字段后跑。")
        r = await c.post("/auth/register", json={"email": U[0], "password": U[1], "name": U[2]})
        if r.status_code != 200:
            r = await c.post("/auth/login", json={"email": U[0], "password": U[1]})
        H = {"Authorization": f"Bearer {r.json()['jwt']}"}
        npass = 0
        for label, b, expect in CASES:
            resp = await c.post(EP, headers=H, json=b)
            ok = resp.status_code in expect
            npass += ok
            extra = "" if ok else f"  <-- got {resp.status_code}: {resp.text[:120]}"
            print(f"  {'PASS' if ok else 'FAIL'}  [{resp.status_code}] {label}{extra}")
        print(f"\n==== 复刻边界矩阵：{npass}/{len(CASES)} ====（零出图零成本）")


asyncio.run(main())
