"""旧流下线回归（ISSUE-0039 路线 A，commit 92de93c step3）——退役端点→404 + openapi 16 路由。

零成本：只验路由层退役（旧端点不可达）+ 契约面。listing 完好/花生卡生效另跑
listing_real_boundary.py + listing_cat_platform_regression.py（含 1 张真出图）。
用法：QA_BASE=http://localhost:8444 uv run python ../image-qa/listing_decommission_regression.py
"""

import asyncio
import os

import httpx

BASE = os.environ.get("QA_BASE", "").rstrip("/")
# 16 路由最终态（92de93c）——listing 主线 + 客户 + 仪表盘 + auth + admin + uploads
KEEP = {
    "/listing/generate", "/listing/jobs", "/listing/jobs/{job_id}", "/listing/{job_id}/events",
    "/uploads", "/uploads/{upload_id}", "/customers", "/customers/{customer_id}",
    "/dashboard/cost", "/auth/login", "/auth/register", "/me",
    "/admin/models", "/admin/models/{name}", "/admin/users", "/admin/users/{user_id}/role",
}
# 退役端点（旧海报/项目/单图/选稿/导出/改稿流）——逐个打应 404（路由已删）
RETIRED = [
    ("POST", "/generate"), ("POST", "/generate/async"), ("POST", "/generate/cost-preview"),
    ("GET", "/generate/x/events"), ("GET", "/jobs/x/images"), ("PUT", "/jobs/x/images/1/keep"),
    ("GET", "/projects"), ("POST", "/projects"), ("GET", "/projects/1"),
    ("PUT", "/projects/1/brief"), ("POST", "/projects/1/generate"), ("POST", "/projects/1/export"),
    ("POST", "/projects/1/revisions"), ("PUT", "/projects/1/status"), ("GET", "/revisions/1"),
]
R: list[tuple[str, bool]] = []


def check(name: str, cond: bool, detail: str = "") -> None:
    R.append((name, bool(cond)))
    print(f"[{'PASS' if cond else 'FAIL'}] {name} {detail}")


async def main() -> None:
    if not BASE:
        raise SystemExit("✋ QA_BASE 未设置。")
    print(f"== 旧流下线回归 == BASE={BASE}")
    async with httpx.AsyncClient(base_url=BASE, trust_env=False, timeout=30.0) as c:
        # app 构造 + 契约面
        op = await c.get("/openapi.json")
        import json
        paths = set(json.loads(op.text)["paths"].keys()) if op.status_code == 200 else set()
        check("app 构造 openapi 200", op.status_code == 200)
        check(f"路由数=16(实{len(paths)})", len(paths) == 16, f"{sorted(paths)}")
        check("listing 主线 4 端点都在", {"/listing/generate", "/listing/jobs", "/listing/jobs/{job_id}", "/listing/{job_id}/events"} <= paths)
        retired_in_schema = [p for p in paths if any(p.startswith(s) for s in ("/generate", "/projects", "/brief", "/revisions", "/export", "/jobs/"))]
        check("openapi 零退役端点", not retired_in_schema, f"残留={retired_in_schema}")

        # 退役端点逐个打 → 404（路由已删；非 401/405/200）
        for method, path in RETIRED:
            r = await c.request(method, path)
            ok = r.status_code == 404
            check(f"退役 {method} {path}→404", ok, f"HTTP {r.status_code}" + ("" if ok else " ⚠️非404=可能仍 mounted"))

        n = sum(1 for _, x in R if x)
        print(f"\n==== 下线回归(路由层): {n}/{len(R)} passed ====（listing 完好/花生卡生效另跑 boundary + 三合一）")


asyncio.run(main())
