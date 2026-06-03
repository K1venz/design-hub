"""QA 全流程 E2E 驱动 — 去 Redis 后单进程版（无 arq worker / 无 REDIS_URL）。

起服务只需：
  cd image-code && DB_URL=mysql+aiomysql://root:<pw>@127.0.0.1:3306/image_gen \
    SEED_ADMIN_EMAIL=qa-admin@test.com SEED_ADMIN_PASSWORD=qa-admin-pass-123 \
    uv run uvicorn design_hub.interface.api.asgi:app --port 8000
异步出图 + SSE 在 API 进程内跑（InProcessTaskQueue + InMemoryEventBus），无需 worker。

认证已改自建邮箱密码（ISSUE-0015）：register=默认设计师；manager 由 SEED_ADMIN_* 注入。
SSE 鉴权走 ?access_token=（ISSUE-0011）。
成本：异步/同步出图全路由到 Mock（family_3→seedream，免费）；导出复用上轮真实图 id=3（file://）。

Run: cd image-code && uv run python /…/image-qa/e2e_driver.py
"""

import asyncio
import io
import json
import time
from typing import Any

import httpx
from PIL import Image, ImageDraw

BASE = "http://127.0.0.1:8000"
EVIDENCE = "/tmp/e2e3-evidence.json"
ADMIN = ("qa-admin@test.com", "qa-admin-pass-123")        # SEED_ADMIN_* 注入的管理者
DESIGNER = ("qa-designer@test.com", "qa-designer-12345")  # 注册的设计师
EXISTING_REAL_IMAGE_ID = 3   # 上轮真实 gpt-image 出图(file://)，导出复用，0 新成本
EXISTING_REAL_PROJECT = 1

results: list[dict[str, Any]] = []
ev: dict[str, Any] = {}


def rec(step: str, ok: bool, detail: str) -> None:
    results.append({"step": step, "ok": ok, "detail": detail})
    print(f"[{'PASS' if ok else 'FAIL'}] {step} :: {detail}")


def peanut_png() -> bytes:
    img = Image.new("RGB", (768, 768), (245, 240, 230))
    d = ImageDraw.Draw(img)
    d.ellipse((260, 220, 508, 548), fill=(196, 150, 90))
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


async def main() -> None:
    async with httpx.AsyncClient(base_url=BASE, trust_env=False, timeout=90.0) as c:
        # ---------- Step 1: 认证（自建邮箱密码）----------
        # 设计师：注册（已存在则登录），断言默认角色=设计师
        r = await c.post("/auth/register", json={"email": DESIGNER[0], "password": DESIGNER[1], "name": "QA设计师"})
        if r.status_code != 200:  # 已注册(409)或其它 → 退回登录复用同一账号
            r = await c.post("/auth/login", json={"email": DESIGNER[0], "password": DESIGNER[1]})
        designer_jwt = r.json().get("jwt") if r.status_code == 200 else None
        rec("1.设计师注册/登录", r.status_code == 200 and r.json().get("role") == "设计师",
            f"HTTP {r.status_code} role={r.json().get('role')}")

        # 管理者：登录 SEED_ADMIN
        r = await c.post("/auth/login", json={"email": ADMIN[0], "password": ADMIN[1]})
        mgr_jwt = r.json().get("jwt") if r.status_code == 200 else None
        rec("1.管理者登录(seed_admin)", r.status_code == 200 and r.json().get("role") == "管理者",
            f"HTTP {r.status_code} role={r.json().get('role')}")

        dh = {"Authorization": f"Bearer {designer_jwt}"}
        mh = {"Authorization": f"Bearer {mgr_jwt}"}

        r = await c.get("/me", headers=dh)
        rec("1./me-设计师", r.status_code == 200 and r.json().get("role") == "设计师", f"HTTP {r.status_code} {r.json()}")
        r = await c.get("/me", headers=mh)
        rec("1./me-管理者", r.status_code == 200 and r.json().get("role") == "管理者", f"HTTP {r.status_code} {r.json()}")

        r = await c.get("/me")
        rec("1.无token/me(401)", r.status_code == 401, f"HTTP {r.status_code}")
        r = await c.get("/customers")
        rec("1.无token业务端点(401)", r.status_code == 401, f"HTTP {r.status_code}")
        r = await c.post("/auth/login", json={"email": DESIGNER[0], "password": "wrong-password"})
        rec("1.错密码登录(401)", r.status_code == 401, f"HTTP {r.status_code} {r.text[:80]}")

        # ---------- Step 2: 角色矩阵 ----------
        for path in ("/admin/models", "/dashboard/cost", "/admin/users"):
            r = await c.get(path, headers=mh)
            rec(f"2.管理者 GET {path}(200)", r.status_code == 200, f"HTTP {r.status_code}")
            r = await c.get(path, headers=dh)
            rec(f"2.设计师 GET {path}(403)", r.status_code == 403, f"HTTP {r.status_code}")

        # ---------- Step 3: 工作台 CRUD ----------
        r = await c.post("/customers", headers=dh, json={
            "name": "QA花生食品(去Redis回归)", "contact": "qa@test", "industry": "食品",
            "brand_color": "#C8965A", "common_styles": ["清新自然"], "common_taboos": [], "common_sizes": ["768x768"]})
        cid = r.json().get("id") if r.status_code == 200 else None
        ev["customer_id"] = cid
        rec("3.创建客户", r.status_code == 200, f"HTTP {r.status_code} customer_id={cid}")

        r = await c.post("/projects", headers=dh, json={"customer_id": cid, "name": "花生主图-回归"})
        pid = r.json().get("id") if r.status_code == 200 else None
        ev["project_id"] = pid
        rec("3.创建项目", r.status_code == 200, f"HTTP {r.status_code} project_id={pid} status={r.json().get('status') if r.status_code==200 else ''}")

        r = await c.put(f"/projects/{pid}/brief", headers=dh, json={
            "material_types": ["主图"], "sizes": ["768x768"], "styles": ["清新自然"], "resolution": "300dpi",
            "bleed": "3mm", "copy_text": "坚果年货", "taboo": "不夸大", "delivery": {"format": "jpg"}})
        rec("3.写需求单(8字段)", r.status_code == 200, f"HTTP {r.status_code}")

        r = await c.post(f"/projects/{pid}/assets", headers=dh, data={"kind": "产品图"},
                         files={"file": ("peanut.png", peanut_png(), "image/png")})
        aid = r.json().get("id") if r.status_code == 200 else None
        ev["asset_id"] = aid
        rec("3.上传素材", r.status_code == 200, f"HTTP {r.status_code} asset_id={aid}")

        # ---------- Step 4: 同步出图（Mock family_3，免费；验 pipeline+落库）----------
        gh = {**dh, "X-User-Id": "qa-designer-001"}
        body = {"subscene": "S1", "family": "family_3", "category": "食品", "tier": "standard",
                "style": "清新自然", "width": 512, "height": 512, "n": 1, "asset_ids": []}
        r = await c.post(f"/projects/{pid}/generate", headers=gh, json=body)
        ok = r.status_code == 200
        sjob = r.json().get("job_id") if ok else None
        ev["sync_job_id"] = sjob
        rec("4.同步出图(mock)", ok and r.json().get("used_model") == "seedream-5",
            f"HTTP {r.status_code} used_model={r.json().get('used_model') if ok else r.text[:120]} "
            f"job={sjob} round_no={r.json().get('round_no') if ok else ''}")

        # ---------- Step 5: 异步 + SSE（单进程 InProcess+InMemory，去 Redis 关键回归）----------
        # 5a 即时订阅
        r = await c.post("/generate/async", headers=gh, json={
            "customer": "QA", "subscene": "S1", "family": "family_3", "tier": "standard",
            "style": "清新自然", "category": "食品", "width": 512, "height": 512, "n": 1})
        ajob = r.json().get("job_id") if r.status_code == 200 else None
        ev["async_job_id"] = ajob
        rec("5a.异步入队(单进程)", r.status_code == 200 and bool(ajob), f"HTTP {r.status_code} job_id={ajob}")

        async def collect_sse(job_id: str, delay: float) -> list[str]:
            if delay:
                await asyncio.sleep(delay)
            evs: list[str] = []
            try:
                async with c.stream("GET", f"/generate/{job_id}/events",
                                    params={"access_token": designer_jwt}, timeout=30.0) as s:
                    async for line in s.aiter_lines():
                        if line.startswith("event:"):
                            et = line.split(":", 1)[1].strip()
                            evs.append(et)
                            if et in ("task_completed", "task_failed"):
                                break
            except Exception as exc:  # noqa: BLE001
                evs.append(f"<err:{exc}>")
            return evs

        if ajob:
            evs = await collect_sse(ajob, delay=0.0)
            ev["sse_immediate"] = evs
            rec("5b.SSE即时订阅全序列", "task_started" in evs and "task_completed" in evs, f"events={evs}")

        # 5c 晚订阅 1.5s（验内存总线回放：去 Redis 后仍不丢 task_started）
        r = await c.post("/generate/async", headers=gh, json={
            "customer": "QA", "subscene": "S1", "family": "family_3", "tier": "standard",
            "style": "清新自然", "category": "食品", "width": 512, "height": 512, "n": 1})
        ajob2 = r.json().get("job_id") if r.status_code == 200 else None
        if ajob2:
            evs2 = await collect_sse(ajob2, delay=1.5)
            ev["sse_delayed"] = evs2
            rec("5c.SSE晚订阅1.5s回放", "task_started" in evs2 and "task_completed" in evs2, f"events={evs2}")

        # 5d SSE 无 token → 401
        try:
            r = await c.get(f"/generate/{ajob}/events", timeout=10.0)
            rec("5d.SSE无token(401)", r.status_code == 401, f"HTTP {r.status_code}")
        except Exception as exc:  # noqa: BLE001
            rec("5d.SSE无token(401)", False, f"err {exc}")

        # ---------- Step 6: 选稿（用异步 mock job）----------
        if ajob:
            r = await c.get(f"/jobs/{ajob}/images", headers=dh)
            imgs = r.json() if r.status_code == 200 else []
            ev["async_image_ids"] = [i["id"] for i in imgs]
            rec("6.列候选图", r.status_code == 200 and len(imgs) >= 1, f"HTTP {r.status_code} ids={ev.get('async_image_ids')}")
            if imgs:
                iid = imgs[0]["id"]
                r = await c.post(f"/jobs/{ajob}/images/{iid}/score", headers=dh, json={"score": 4})
                rec("6.评分(4星)", r.status_code == 200 and r.json().get("score") == 4, f"HTTP {r.status_code}")
                r = await c.post(f"/jobs/{ajob}/images/{iid}/keep", headers=dh, json={"kept": True})
                rec("6.保留", r.status_code == 200 and r.json().get("kept") is True, f"HTTP {r.status_code}")
                r = await c.get(f"/jobs/{ajob}/usable-rate", headers=dh)
                rec("6.可用率", r.status_code == 200, f"HTTP {r.status_code} {r.json() if r.status_code==200 else ''}")

        # ---------- Step 6b: 项目级枚举（新增 project_catalog, ISSUE-0012）----------
        r = await c.get(f"/projects/{pid}/jobs", headers=dh)
        rec("6b.项目任务列举 /projects/{id}/jobs", r.status_code == 200,
            f"HTTP {r.status_code} jobs={len(r.json()) if r.status_code==200 else r.text[:80]}")
        r = await c.get(f"/projects/{pid}/images", headers=dh)
        rec("6b.项目候选图列举 /projects/{id}/images", r.status_code == 200,
            f"HTTP {r.status_code} imgs={len(r.json()) if r.status_code==200 else r.text[:80]}")

        # ---------- Step 7: 改稿单 409/force ----------
        s1 = (await c.put(f"/projects/{pid}/status", headers=dh, json={"status": "设计中"})).status_code
        s2 = (await c.put(f"/projects/{pid}/status", headers=dh, json={"status": "客户审稿"})).status_code
        rec("7.状态机流转", s1 == 200 and s2 == 200, f"设计中 {s1}; 客户审稿 {s2}")
        r = await c.post(f"/projects/{pid}/revisions", headers=dh, json={})
        rid = r.json().get("id") if r.status_code == 200 else None
        rec("7.开改稿单", r.status_code == 200, f"HTTP {r.status_code} rev={rid}")
        if rid:
            await c.post(f"/revisions/{rid}/items", headers=dh, json={"text": "背景换暖色", "related_image_id": None})
        r = await c.put(f"/projects/{pid}/status", headers=dh, json={"status": "已交付"})
        rec("7.未完成条目转已交付(409)", r.status_code == 409, f"HTTP {r.status_code} {r.text[:100]}")
        r = await c.put(f"/projects/{pid}/status?force=true", headers=dh, json={"status": "已交付"})
        rec("7.force转已交付(200)", r.status_code == 200, f"HTTP {r.status_code} status={r.json().get('status') if r.status_code==200 else ''}")

        # ---------- Step 8: 导出（复用上轮真实 file:// 图，0 新成本）----------
        r = await c.post(f"/projects/{EXISTING_REAL_PROJECT}/export", headers=dh, json={
            "image_ids": [EXISTING_REAL_IMAGE_ID], "formats": ["jpg", "png", "pdf"], "zip": True})
        ok = r.status_code == 200
        if ok:
            jr = r.json()
            ev["export_files"] = [f["filename"] for f in jr.get("files", [])]
            rec("8.导出(真实图 jpg/png/pdf+zip)", len(jr.get("files", [])) >= 3 and jr.get("package_url"),
                f"HTTP 200 files={len(jr.get('files',[]))} pkg={jr.get('package_url')}")
        else:
            rec("8.导出", False, f"HTTP {r.status_code} {r.text[:160]}")

        # ---------- Step 9: 仪表盘 5 维 ----------
        dim_ok = True
        det = []
        for d in ("overview", "model", "project", "designer", "tier"):
            r = await c.get(f"/dashboard/cost?dim={d}", headers=mh)
            det.append(f"{d}:{r.status_code}")
            dim_ok = dim_ok and r.status_code == 200
        rec("9.仪表盘5维", dim_ok, " ".join(det))

        # ---------- Step 10: 监控 /metrics ----------
        r = await c.get("/metrics")
        has_prom = r.status_code == 200 and ("# HELP" in r.text or "# TYPE" in r.text)
        gen = [ln for ln in r.text.splitlines() if ln.startswith("design_hub_generations_total")]
        rec("10.监控/metrics", has_prom and bool(gen), f"HTTP {r.status_code} generations_total行={gen[:2]}")

        with open(EVIDENCE, "w") as f:
            json.dump({"results": results, "evidence": ev}, f, ensure_ascii=False, indent=2)
        npass = sum(1 for x in results if x["ok"])
        print(f"\n==== SUMMARY: {npass}/{len(results)} checks passed ====  (全程 0 真实出图，导出复用上轮真实图)")


asyncio.run(main())
