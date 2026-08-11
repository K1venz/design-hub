"""bug C · 客户列表 owner 隔离回归（ISSUE-0041，coordinator #423 验收点）。

现状漏洞：routes/customers.py 三 handler 挂了 login_required 但不按 user 过滤 →
任何登录用户看全表（新注册号看到他人「拍拍熊」=跨用户泄漏，同 ISSUE-0039 类）。
断言全部按**修复后**预期写（镜像 listing_job owner 隔离 + 0032 anti-enum 404）：
  ① A 建客户 → A 自己列表/详情可见（隔离不能误伤本人）
  ② B 列表**看不到** A 的客户、只返本人（列表隔离）——核心
  ③ B 越权 GET /customers/{A的id} → **404**（anti-enum，不泄漏存在性）——核心
  ④ create 记 owner（A 的客户归 A）——由 ①② 反映
  ⑤ 不存在 id → 404（pre/post 都应成立，sanity）
→ **现在跑 = 复现 bug**：②③ 应 FAIL（B 看得到 A 客户 / 越权得 200）。
  **dev 修后跑 = 应全 PASS**。
用法：QA_BASE=http://localhost:8444 uv run python ../image-qa/customer_isolation_regression.py
"""

import asyncio
import os
import time

import httpx

from qa_auth import AccountSlot, login_verified_account

BASE = os.environ.get("QA_BASE", "").rstrip("/")
RUN = int(time.time())  # run-unique，避免跨次跑客户累积污染断言


async def token(c, slot):  # noqa: ANN001
    session = await login_verified_account(c, slot=slot)
    return {"Authorization": f"Bearer {session.jwt}"}


async def main() -> None:
    if not BASE:
        raise SystemExit("✋ QA_BASE 未设置。")
    print(f"== 客户隔离回归 (bug C / ISSUE-0041) == BASE={BASE} RUN={RUN}")
    async with httpx.AsyncClient(base_url=BASE, trust_env=False, timeout=60.0) as c:
        HA = await token(c, AccountSlot.PRIMARY)
        HB = await token(c, AccountSlot.SECONDARY)
        # A、B 各建一个客户
        ca = (await c.post("/customers", headers=HA, json={"name": f"A的拍拍熊-{RUN}", "contact": "A-secret"})).json()
        cb = (await c.post("/customers", headers=HB, json={"name": f"B的客户-{RUN}"})).json()
        a_id, b_id = ca["id"], cb["id"]

        a_list = (await c.get("/customers", headers=HA)).json()
        b_list = (await c.get("/customers", headers=HB)).json()
        a_ids = {x["id"] for x in a_list}
        b_ids = {x["id"] for x in b_list}

        # 越权 / 自己 / 不存在
        b_get_a = await c.get(f"/customers/{a_id}", headers=HB)   # B 越权看 A 的客户 → 应 404
        a_get_a = await c.get(f"/customers/{a_id}", headers=HA)   # A 看自己 → 应 200
        ghost = await c.get("/customers/999999999", headers=HA)   # 不存在 → 应 404

        cases = [
            ("① A 自己列表含本人客户",      a_id in a_ids),
            ("① A 详情可访问本人 (200)",    a_get_a.status_code == 200),
            ("② B 列表看不到 A 的客户",     a_id not in b_ids),                 # 核心
            ("② B 列表包含本次本人客户",     b_id in b_ids),                    # 核心
            ("② A 列表不含 B 的客户",       b_id not in a_ids),
            ("③ B 越权 GET A 的客户 → 404", b_get_a.status_code == 404),        # 核心
            ("⑤ 不存在 id → 404",          ghost.status_code == 404),
        ]
        print("\n==== 客户隔离回归 ====")
        allpass = True
        for label, ok in cases:
            allpass &= ok
            print(f"  {'PASS' if ok else 'FAIL'}  {label}")
        print(f"\n  B 越权拿到 A 客户实际返回：HTTP {b_get_a.status_code}"
              + (f"  name={b_get_a.json().get('name')!r}（泄漏!）" if b_get_a.status_code == 200 else ""))
        print(f"  B 的列表 ids={sorted(b_ids)}  A 的列表 ids={sorted(a_ids)}")
        print(f"\n  总判：{'✅ 全 PASS（隔离生效）' if allpass else '🔴 有 FAIL —— 现在=复现 bug C（修前预期）；dev 修后应全 PASS'}")


asyncio.run(main())
