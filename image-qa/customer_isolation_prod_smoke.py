"""bug C · 客户隔离 prod smoke（ISSUE-0041 验收标准 5，coordinator #423/#430）。

部署后跑：专用、预验证的空账号 `GET /customers` 必须**为空**（拍拍熊已被迁移删 + 隔离生效）。
⚠️ **只读**：使用运行时提供、预先验证且约定为空的次账号拉列表，**不注册、不发邮件、不在 prod 建任何客户**。
用法（部署后，经 8445 隧道指 prod api）：
  PROD_BASE=http://localhost:8445 uv run python ../image-qa/customer_isolation_prod_smoke.py
"""

import asyncio
import os

import httpx

from qa_auth import AccountSlot, login_verified_account

BASE = os.environ.get("PROD_BASE", "").rstrip("/")


async def main() -> None:
    if not BASE:
        raise SystemExit("✋ PROD_BASE 未设置——必须经隧道显式指向部署后 prod api。")
    print(f"== 客户隔离 prod smoke (bug C / ISSUE-0041 标准5) == BASE={BASE}")
    async with httpx.AsyncClient(base_url=BASE, trust_env=False, timeout=60.0) as c:
        print(f"[probe] openapi {(await c.get('/openapi.json')).status_code}")
        session = await login_verified_account(c, slot=AccountSlot.SECONDARY)
        H = {"Authorization": f"Bearer {session.jwt}"}
        resp = await c.get("/customers", headers=H)
        lst = resp.json()
        empty = resp.status_code == 200 and lst == []
        print("\n==== 客户隔离 prod smoke ====")
        print(f"  预验证空账号 GET /customers → HTTP {resp.status_code}, 返回 {lst!r}")
        print(f"  标准5（隔离账号列表为空·拍拍熊已清·隔离生效）：{'✅ PASS' if empty else '🔴 FAIL'}")
        print(f"\n  已验证账号 {session.email} 保留。本探针只读、未注册、未在 prod 建客户。")


asyncio.run(main())
