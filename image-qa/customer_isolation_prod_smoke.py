"""bug C · 客户隔离 prod smoke（ISSUE-0041 验收标准 5，coordinator #423/#430）。

部署后跑：新注册账号 `GET /customers` 必须**为空**（拍拍熊已被迁移删 + 隔离生效）。
⚠️ **只读**：只注册 1 个可标识 qa-test 号 + 拉列表，**不在 prod 建任何客户**（不污染 prod 数据）。
用法（部署后，经 8445 隧道指 prod api）：
  PROD_BASE=http://localhost:8445 uv run python ../image-qa/customer_isolation_prod_smoke.py
"""

import asyncio
import os
import time

import httpx

BASE = os.environ.get("PROD_BASE", "").rstrip("/")
U = (f"qa-custiso-prod-{int(time.time())}@example.com", "qa-custiso-prod-123", "QA客户隔离prodsmoke")


async def main() -> None:
    if not BASE:
        raise SystemExit("✋ PROD_BASE 未设置——必须经隧道显式指向部署后 prod api。")
    print(f"== 客户隔离 prod smoke (bug C / ISSUE-0041 标准5) == BASE={BASE}")
    async with httpx.AsyncClient(base_url=BASE, trust_env=False, timeout=60.0) as c:
        print(f"[probe] openapi {(await c.get('/openapi.json')).status_code}")
        r = await c.post("/auth/register", json={"email": U[0], "password": U[1], "name": U[2]})
        if r.status_code != 200:
            r = await c.post("/auth/login", json={"email": U[0], "password": U[1]})
        H = {"Authorization": f"Bearer {r.json()['jwt']}"}
        resp = await c.get("/customers", headers=H)
        lst = resp.json()
        empty = resp.status_code == 200 and lst == []
        print("\n==== 客户隔离 prod smoke ====")
        print(f"  新账号 GET /customers → HTTP {resp.status_code}, 返回 {lst!r}")
        print(f"  标准5（新账号列表为空·拍拍熊已清·隔离生效）：{'✅ PASS' if empty else '🔴 FAIL'}")
        print(f"\n  qa-test 号 {U[0]} 可后清（ops）。本探针只读、未在 prod 建客户。")


asyncio.run(main())
