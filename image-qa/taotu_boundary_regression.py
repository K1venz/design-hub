"""套图边界/契约回归（零成本，骨架 TT-04/05/06/14/16/17/19 + 互斥）。

GHOST 技法：合法契约 + 幽灵 upload id → 校验通过后卡 owns→404；契约非法→400/422。
零出图零成本。断言按骨架终稿（#485/#495/dev 0e9ee9d）。
用法：QA_BASE=http://localhost:8444 uv run python ../image-qa/taotu_boundary_regression.py
"""

import asyncio
import os

import httpx

from qa_auth import login_verified_account

BASE = os.environ.get("QA_BASE", "").rstrip("/")
GHOST = "0000000000000000.png"


def body(plan=None, n=None, overlay=None):  # noqa: ANN001
    b = {"upload_ids": [GHOST], "prompt": "电商主图：产品主体清晰", "ratio": "1:1",
         "category": "FOOD",
         "modifiers": {"platform": "淘宝天猫1688", "region": "中国", "language": "中文"}}
    if plan is not None:
        b["plan"] = plan
    if n is not None:
        b["n"] = n
    if overlay is not None:
        b["overlay_texts"] = overlay
    return b


P3 = {"白底": 1, "场景": 1, "卖点": 1}
CASES = [
    ("互斥·plan+n 同传→400", body(plan=P3, n=1), {400}),
    ("互斥·都不带→400", body(), {400}),
    ("未知图型「其他」→400/422", body(plan={"其他": 3}), {400, 422}),
    ("未知图型混入→400/422", body(plan={"白底": 2, "细节": 1}), {400, 422}),
    ("单型负数→400/422", body(plan={"白底": -1, "场景": 2, "卖点": 2}), {400, 422}),
    ("非整数→400/422", body(plan={"白底": 1.5, "场景": 1, "卖点": 1}), {400, 422}),
    ("Σ=2<下限→400", body(plan={"白底": 1, "场景": 1, "卖点": 0}), {400}),
    ("Σ=11>上限→400", body(plan={"白底": 4, "场景": 4, "卖点": 3}), {400}),
    ("全0→400", body(plan={"白底": 0, "场景": 0, "卖点": 0}), {400}),
    ("Σ=3 合法→过契约·卡owns 404", body(plan=P3), {404}),
    ("Σ=10 合法→过契约·卡owns 404", body(plan={"白底": 4, "场景": 3, "卖点": 3}), {404}),
    ("单型0(Σ=3)合法→404", body(plan={"白底": 0, "场景": 2, "卖点": 1}), {404}),
    ("overlay·无卖点图→400", body(plan={"白底": 2, "场景": 1, "卖点": 0}, overlay=["好吃"]), {400}),
    ("overlay·3条→400/422", body(plan=P3, overlay=["一", "二", "三"]), {400, 422}),
    ("overlay·单条13字→400/422", body(plan=P3, overlay=["这一条文案足足有十三个字啦"]), {400, 422}),
    ("overlay·单条12字(上限内)→404", body(plan=P3, overlay=["这一条文案足足有十二个字"]), {404}),
    ("overlay·n单图流带→400", body(n=1, overlay=["好吃"]), {400}),
    ("overlay·合法2条→过契约·404", body(plan=P3, overlay=["高山七彩花生", "原生态种植"]), {404}),
    ("n流·n=1 零破坏→过契约·404", body(n=1), {404}),
    ("n流·n=8>7→400", body(n=8), {400}),
]


async def main() -> None:
    if not BASE:
        raise SystemExit("✋ QA_BASE 未设置。")
    print(f"== 套图边界/契约回归 (0e9ee9d) == BASE={BASE}")
    async with httpx.AsyncClient(base_url=BASE, trust_env=False, timeout=60.0) as c:
        session = await login_verified_account(c)
        H = {"Authorization": f"Bearer {session.jwt}"}
        npass = 0
        for label, b, expect in CASES:
            resp = await c.post("/listing/generate", headers=H, json=b)
            ok = resp.status_code in expect
            npass += ok
            detail = "" if ok else f"  <-- got {resp.status_code}: {resp.text[:120]}"
            print(f"  {'PASS' if ok else 'FAIL'}  [{resp.status_code}] {label}{detail}")
        print(f"\n==== 套图边界矩阵：{npass}/{len(CASES)} ====（零出图零成本）")


asyncio.run(main())
