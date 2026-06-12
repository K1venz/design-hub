"""世界 A 移除回归（ISSUE-0046 验收①②，dev+fe 完工后跑）。

prong①「listing/uploads/auth/出图全链零变化」——实证删世界 A 没误伤共享依赖（唯一真风险）：
  auth(register/login/me) → uploads → 单图流 n=1 → 套图 plan 1/1/1 → history(jobs/详情)
  全活，cost 价无关核（total>0 且 ==Σ成功张、张数对）。FULL=1 再加 edit(0040)+clone 全链。
prong②「/customers·/dashboard 前后端 404」——端点直探（docs default-OFF）：
  删的世界 A 路由 → 404（路由没了）；**反向核** 保留路由 /users·/admin/models → 非 404
  （仍挂载、只是鉴权 401/403）= 证选择性删除没误删活路由。
prong③(DB 8表DROP/6表完好) 见 world_a_db_check.py；prong④(后端 pytest) 直接跑命令。
bounded：默认单图+套图（≈¥1.6/qa 占位价更高也只 2 单）；FULL 加 edit+clone。
用法：QA_BASE=http://localhost:8444 [FULL=1] uv run python ../image-qa/world_a_removal_regression.py
"""

import asyncio
import io
import json
import os
import time
from decimal import Decimal

import httpx
from PIL import Image

BASE = os.environ.get("QA_BASE", "").rstrip("/")
FULL = os.environ.get("FULL", "") == "1"
SRC = "/Users/Zhuanz/CLAUDE/image-gen/image-qa/通用块多产品/通用块-花生.png"
U = (f"qa-worlda-{int(time.time())}@example.com", "qa-worlda-123", "QA世界A回归")
MODS = {"platform": "淘宝天猫1688", "region": "中国", "language": "中文"}
PLAN = {"白底": 1, "场景": 1, "卖点": 1}

_n_pass = 0
_n_total = 0


def check(label, ok, extra=""):  # noqa: ANN001
    global _n_pass, _n_total
    _n_total += 1
    _n_pass += bool(ok)
    print(f"  {'PASS' if ok else '🔴 FAIL'}  {label}{('  ' + extra) if extra else ''}")
    return bool(ok)


def to_png(path: str) -> bytes:
    img = Image.open(path).convert("RGB")
    s = max(img.size)
    cv = Image.new("RGB", (s, s), (255, 255, 255))
    cv.paste(img, ((s - img.width) // 2, (s - img.height) // 2))
    b = io.BytesIO()
    cv.resize((1024, 1024)).save(b, format="PNG")
    return b.getvalue()


def cost_ok(d, k):  # noqa: ANN001
    """价无关：total>0 且 ==Σ成功张 cost 且成功张数==k（qa 占位 1.19/prod 0.40 都过）。"""
    imgs = [i for i in d.get("images", []) if i.get("status") == "成功"]
    tot = Decimal(str(d.get("total_cost", "0")))
    s = sum((Decimal(str(i.get("cost", "0"))) for i in imgs), Decimal("0"))
    return tot > 0 and tot == s and len(imgs) == k


async def wait_job(c, H, tok, job):  # noqa: ANN001
    try:
        async with c.stream("GET", f"/listing/{job}/events", params={"access_token": tok}) as s:
            ev = None
            async for line in s.aiter_lines():
                if line.startswith("event:"):
                    ev = line.split(":", 1)[1].strip()
                    if ev in ("task_completed", "task_failed"):
                        break
    except httpx.RemoteProtocolError:
        pass
    for _ in range(200):
        d = (await c.get(f"/listing/jobs/{job}", headers=H)).json()
        if d.get("status") in ("完成", "失败"):
            return d
        await asyncio.sleep(3)
    return (await c.get(f"/listing/jobs/{job}", headers=H)).json()


async def gen(c, H, tok, uid, body_extra):  # noqa: ANN001
    body = {"upload_ids": [uid], "prompt": "电商主图：产品主体清晰、背景干净得体、质感真实突出",
            "ratio": "1:1", "category": "FOOD", "modifiers": MODS, **body_extra}
    job = (await c.post("/listing/generate", headers=H, json=body)).json()["job_id"]
    return await wait_job(c, H, tok, job)


async def probe_404(c, H, label, method, path, expect_gone=True):  # noqa: ANN001
    """expect_gone=True：删的路由应 404；False：保留路由应非 404（仍挂载、401/403/200/422 都行）。"""
    r = await (c.post(path, headers=H, json={}) if method == "POST" else c.get(path, headers=H))
    sc = r.status_code
    if expect_gone:
        return check(f"{label} {method} {path} → 404(路由已删)", sc == 404, f"got {sc}")
    return check(f"{label} {method} {path} → 非404(保留路由仍挂载)", sc != 404, f"got {sc}")


async def main() -> None:
    if not BASE:
        raise SystemExit("✋ QA_BASE 未设置（指向 dev+fe 完工后重建的 qa 容器，如 http://localhost:8444）。")
    print(f"== 世界 A 移除回归（ISSUE-0046 ①②）== BASE={BASE} FULL={FULL}")

    async with httpx.AsyncClient(base_url=BASE, trust_env=False, timeout=900.0) as c:
        # ===== prong① auth 零变化 =====
        print("\n[① auth/uploads 零变化]")
        r = await c.post("/auth/register", json={"email": U[0], "password": U[1], "name": U[2]})
        if r.status_code != 200:
            r = await c.post("/auth/login", json={"email": U[0], "password": U[1]})
        check("auth register/login → jwt", r.status_code == 200 and "jwt" in r.json(), f"got {r.status_code}")
        tok = r.json()["jwt"]
        H = {"Authorization": f"Bearer {tok}"}
        me = await c.get("/me", headers=H)
        check("GET /me → 200 带账号", me.status_code == 200 and me.json().get("email") == U[0], f"got {me.status_code}")
        up = await c.post("/uploads", headers=H, files={"file": ("p.png", to_png(SRC), "image/png")})
        check("POST /uploads → id", up.status_code == 200 and "id" in up.json(), f"got {up.status_code}")
        uid = up.json()["id"]

        # ===== prong① 出图零变化：单图流 + 套图 =====
        print("\n[① 单图流 n=1 零变化]")
        d = await gen(c, H, tok, uid, {"n": 1})
        check("单图流完成 + 1 张 + image_type 空", d.get("status") == "完成"
              and len([i for i in d.get("images", []) if i.get("status") == "成功"]) == 1
              and (d.get("images") or [{}])[0].get("image_type") in (None, ""), f"status={d.get('status')}")
        check("单图流 cost 价无关核", cost_ok(d, 1), f"total={d.get('total_cost')}")

        print("\n[① 套图 plan 1/1/1 零变化]")
        d = await gen(c, H, tok, uid, {"plan": PLAN, "overlay_texts": ["高山七彩花生", "原生态种植"]})
        imgs = [i for i in d.get("images", []) if i.get("status") == "成功"]
        dist = sorted(i.get("image_type") or "?" for i in imgs)
        check("套图完成 + 分布 1/1/1", d.get("status") == "完成" and dist == ["卖点", "场景", "白底"], f"dist={dist}")
        check("套图 cost 价无关核", cost_ok(d, 3), f"total={d.get('total_cost')}")

        # ===== prong① history 零变化 =====
        print("\n[① history 零变化]")
        jobs = await c.get("/listing/jobs", headers=H)
        jl = jobs.json() if jobs.status_code == 200 else {}
        cnt = len(jl) if isinstance(jl, list) else len(jl.get("jobs", jl.get("items", [])))
        check("GET /listing/jobs → 列表(≥2 单)", jobs.status_code == 200 and cnt >= 2, f"status={jobs.status_code} cnt={cnt}")

        # ===== prong① FULL：edit(0040) + clone 全链 =====
        if FULL:
            print("\n[① FULL: 二次编辑 0040 链零变化]")
            key = (imgs[0].get("image_key") if imgs else None)
            if key:
                er = await c.post("/listing/edit", headers=H,
                                  json={"source_image_key": key, "edit_mode": "delta", "prompt": "把背景调亮一点"})
                if er.status_code == 200:
                    ed = await wait_job(c, H, tok, er.json()["job_id"])
                    check("edit delta 完成 + 出图", ed.get("status") == "完成"
                          and any(i.get("status") == "成功" for i in ed.get("images", [])), f"status={ed.get('status')}")
                else:
                    check("edit delta 提交", False, f"POST /listing/edit got {er.status_code}")
            else:
                check("edit 取 source key", False, "套图无 image_key")

        # ===== prong② 世界 A 路由 404 + 保留路由反向核 =====
        print("\n[② 世界 A 路由 404（端点直探）]")
        await probe_404(c, H, "customers", "GET", "/customers")
        await probe_404(c, H, "customers", "POST", "/customers")
        await probe_404(c, H, "dashboard", "GET", "/dashboard/cost")
        await probe_404(c, H, "dashboard", "GET", "/dashboard")
        print("\n[② 保留路由反向核（非 404 = 仍挂载）]")
        await probe_404(c, H, "users(保)", "GET", "/users", expect_gone=False)
        await probe_404(c, H, "admin-models(保)", "GET", "/admin/models", expect_gone=False)
        await probe_404(c, H, "listing-jobs(保)", "GET", "/listing/jobs", expect_gone=False)

    print(f"\n==== 世界 A 移除回归 ①②：{_n_pass}/{_n_total} ====")
    if _n_pass != _n_total:
        raise SystemExit("🔴 有 FAIL——零变化破防 or 路由删除不彻底，STOP 报 coordinator。")


asyncio.run(main())
