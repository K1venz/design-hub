"""QA E2E integration driver: real MySQL + Redis + real gpt-image.

Drives the production ASGI app over HTTP (trust_env=False to bypass local SOCKS).
Cost guard: exactly ONE real gpt-image call (step 4, n=1); step 5 routes to a Mock
model (family_3 -> seedream-5) so async/SSE/arq is exercised for free.

Run from image-code venv:
  cd image-code && uv run python /…/image-qa/e2e_driver.py
"""

import asyncio
import base64
import io
import json
import time
from typing import Any

import httpx
from PIL import Image, ImageDraw

BASE = "http://127.0.0.1:8000"
EVIDENCE = "/tmp/e2e-evidence.json"

results: list[dict[str, Any]] = []
ev: dict[str, Any] = {}  # carried ids/artifacts for DB cross-check


def rec(step: str, ok: bool, detail: str) -> None:
    results.append({"step": step, "ok": ok, "detail": detail})
    print(f"[{'PASS' if ok else 'FAIL'}] {step} :: {detail}")


def peanut_png() -> bytes:
    """A small valid square PNG standing in for a product photo (peanut/FOOD)."""
    img = Image.new("RGB", (1024, 1024), (245, 240, 230))
    d = ImageDraw.Draw(img)
    d.ellipse((360, 300, 664, 724), fill=(196, 150, 90))
    d.ellipse((420, 360, 604, 520), fill=(176, 130, 72))
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


async def auth(client: httpx.AsyncClient, code: str) -> httpx.Response:
    return await client.post(f"/auth/feishu/callback", json={"code": code})


async def main() -> None:
    async with httpx.AsyncClient(base_url=BASE, trust_env=False, timeout=220.0) as c:
        # ---------- Step 1: 认证 ----------
        r = await auth(c, "designer-qa-001")
        designer_jwt = r.json().get("jwt") if r.status_code == 200 else None
        rec("1.认证-设计师登录", r.status_code == 200 and r.json().get("role") == "设计师",
            f"HTTP {r.status_code} role={r.json().get('role')} name={r.json().get('name')}")

        r = await auth(c, "mgr-qa-001")
        mgr_jwt = r.json().get("jwt") if r.status_code == 200 else None
        rec("1.认证-管理者登录", r.status_code == 200 and r.json().get("role") == "管理者",
            f"HTTP {r.status_code} role={r.json().get('role')}")

        r = await auth(c, "out-qa-001")
        rec("1.认证-其他部门拒绝(403)", r.status_code == 403, f"HTTP {r.status_code} {r.text[:120]}")

        dh = {"Authorization": f"Bearer {designer_jwt}"}
        mh = {"Authorization": f"Bearer {mgr_jwt}"}

        r = await c.get("/me", headers=dh)
        rec("1./me-设计师", r.status_code == 200 and r.json().get("role") == "设计师",
            f"HTTP {r.status_code} {r.json()}")
        r = await c.get("/me", headers=mh)
        rec("1./me-管理者", r.status_code == 200 and r.json().get("role") == "管理者",
            f"HTTP {r.status_code} {r.json()}")

        r = await c.get("/me")
        rec("1.无token/me(401)", r.status_code == 401, f"HTTP {r.status_code} {r.text[:100]}")
        r = await c.get("/customers")
        rec("1.无token业务端点/customers(401)", r.status_code == 401,
            f"HTTP {r.status_code} {r.text[:100]}")

        # ---------- Step 2: 角色矩阵 ----------
        r = await c.get("/admin/models", headers=mh)
        rec("2.管理者GET/admin/models(200)", r.status_code == 200,
            f"HTTP {r.status_code} models={len(r.json()) if r.status_code==200 else r.text[:80]}")
        r = await c.get("/dashboard/cost", headers=mh)
        rec("2.管理者GET/dashboard/cost(200)", r.status_code == 200,
            f"HTTP {r.status_code} {str(r.json())[:120] if r.status_code==200 else r.text[:80]}")
        r = await c.get("/admin/models", headers=dh)
        rec("2.设计师GET/admin/models(403)", r.status_code == 403, f"HTTP {r.status_code} {r.text[:100]}")
        r = await c.get("/dashboard/cost", headers=dh)
        rec("2.设计师GET/dashboard/cost(403)", r.status_code == 403, f"HTTP {r.status_code} {r.text[:100]}")

        # ---------- Step 3: 工作台 ----------
        r = await c.post("/customers", headers=dh, json={
            "name": "QA花生食品旗舰店", "contact": "qa@test", "industry": "食品",
            "brand_color": "#C8965A", "common_styles": ["清新自然"],
            "common_taboos": ["禁夸张医疗功效"], "common_sizes": ["1024x1024"],
        })
        ok = r.status_code == 200
        cid = r.json().get("id") if ok else None
        ev["customer_id"] = cid
        rec("3.创建客户", ok, f"HTTP {r.status_code} customer_id={cid}")

        r = await c.post("/projects", headers=dh, json={"customer_id": cid, "name": "花生年货礼盒主图"})
        ok = r.status_code == 200
        pid = r.json().get("id") if ok else None
        ev["project_id"] = pid
        rec("3.创建项目", ok, f"HTTP {r.status_code} project_id={pid} status={r.json().get('status') if ok else ''}")

        r = await c.put(f"/projects/{pid}/brief", headers=dh, json={
            "material_types": ["主图", "海报"], "sizes": ["1024x1024"], "styles": ["清新自然"],
            "resolution": "300dpi", "bleed": "3mm", "copy_text": "坚果年货 颗颗饱满",
            "taboo": "不夸大功效", "delivery": {"format": "jpg", "deadline": "2026-06-10"},
        })
        rec("3.写需求单(8字段)", r.status_code == 200,
            f"HTTP {r.status_code} brief_id={r.json().get('id') if r.status_code==200 else r.text[:100]}")

        files = {"file": ("peanut.png", peanut_png(), "image/png")}
        r = await c.post(f"/projects/{pid}/assets", headers=dh, data={"kind": "产品图"}, files=files)
        ok = r.status_code == 200
        aid = r.json().get("id") if ok else None
        ev["asset_id"] = aid
        rec("3.上传素材(产品图)", ok, f"HTTP {r.status_code} asset_id={aid} url={r.json().get('url') if ok else r.text[:120]}")

        # ---------- Step 4: 真实出图 (n=1, 第1张, GPT_IMAGE_2 edit) ----------
        gen_headers = {**dh, "X-User-Id": "designer-qa-001"}
        body = {"subscene": "S1", "family": "family_4", "category": "食品",
                "tier": "standard", "style": "清新自然", "width": 1024, "height": 1024,
                "n": 1, "asset_ids": [aid] if aid else []}
        t0 = time.perf_counter()
        r = await c.post(f"/projects/{pid}/generate", headers=gen_headers, json=body)
        dt = int((time.perf_counter() - t0) * 1000)
        ok = r.status_code == 200
        if ok:
            j = r.json()
            ev["sync_job_id"] = j.get("job_id")
            ev["sync_used_model"] = j.get("used_model")
            ev["sync_img_count"] = len(j.get("images", []))
            ev["sync_img_url"] = (j.get("images") or [{}])[0].get("url")
            real = j.get("used_model") == "gpt-image-2"
            rec("4.真实出图(n=1)", real,
                f"HTTP 200 used_model={j.get('used_model')} round_no={j.get('round_no')} "
                f"job_id={j.get('job_id')} imgs={ev['sync_img_count']} cost={j.get('total_cost')} "
                f"url={ev['sync_img_url']} latency={dt}ms")
        else:
            rec("4.真实出图(n=1)", False, f"HTTP {r.status_code} {r.text[:300]} latency={dt}ms")

        # ---------- Step 6: 选稿 (依赖 step4 job) ----------
        sjob = ev.get("sync_job_id")
        if sjob:
            r = await c.get(f"/jobs/{sjob}/images", headers=dh)
            imgs = r.json() if r.status_code == 200 else []
            ev["sync_image_ids"] = [i["id"] for i in imgs]
            rec("6.列候选图", r.status_code == 200 and len(imgs) >= 1,
                f"HTTP {r.status_code} images={ev.get('sync_image_ids')}")
            if ev.get("sync_image_ids"):
                iid = ev["sync_image_ids"][0]
                r = await c.post(f"/jobs/{sjob}/images/{iid}/score", headers=dh, json={"score": 4})
                rec("6.评分(4星)", r.status_code == 200 and r.json().get("score") == 4,
                    f"HTTP {r.status_code} score={r.json().get('score') if r.status_code==200 else r.text[:80]}")
                r = await c.post(f"/jobs/{sjob}/images/{iid}/keep", headers=dh, json={"kept": True})
                rec("6.保留(keep)", r.status_code == 200 and r.json().get("kept") is True,
                    f"HTTP {r.status_code} kept={r.json().get('kept') if r.status_code==200 else r.text[:80]}")
                r = await c.get(f"/jobs/{sjob}/usable-rate", headers=dh)
                rec("6.可用率", r.status_code == 200,
                    f"HTTP {r.status_code} {r.json() if r.status_code==200 else r.text[:80]}")
        else:
            rec("6.选稿", False, "跳过：step4 未产出 job")

        # ---------- Step 7: 改稿单 + 交付强校验 (409/force) ----------
        # 状态机推进到 客户审稿，使 已交付 成为合法下一态，隔离出交付强校验
        r = await c.put(f"/projects/{pid}/status", headers=dh, json={"status": "设计中"})
        s1 = r.status_code
        r = await c.put(f"/projects/{pid}/status", headers=dh, json={"status": "客户审稿"})
        s2 = r.status_code
        rec("7.状态机流转(录入→设计中→审稿)", s1 == 200 and s2 == 200, f"设计中 HTTP {s1}; 客户审稿 HTTP {s2}")

        r = await c.post(f"/projects/{pid}/revisions", headers=dh, json={})
        ok = r.status_code == 200
        rid = r.json().get("id") if ok else None
        ev["revision_id"] = rid
        rec("7.开改稿单", ok, f"HTTP {r.status_code} revision_id={rid} status={r.json().get('status') if ok else r.text[:80]}")
        if rid:
            rel = (ev.get("sync_image_ids") or [None])[0]
            r = await c.post(f"/revisions/{rid}/items", headers=dh,
                             json={"text": "背景换暖色调，突出年货氛围", "related_image_id": rel})
            rec("7.加改稿条目", r.status_code == 200,
                f"HTTP {r.status_code} items={len(r.json().get('items', [])) if r.status_code==200 else r.text[:80]}")

        r = await c.put(f"/projects/{pid}/status", headers=dh, json={"status": "已交付"})
        rec("7.未完成条目转已交付(409)", r.status_code == 409, f"HTTP {r.status_code} {r.text[:140]}")

        r = await c.put(f"/projects/{pid}/status?force=true", headers=dh, json={"status": "已交付"})
        rec("7.force=true转已交付(200)", r.status_code == 200,
            f"HTTP {r.status_code} status={r.json().get('status') if r.status_code==200 else r.text[:100]}")

        # ---------- Step 8: 导出 (多格式 + zip, 依赖 step4 图) ----------
        iids = ev.get("sync_image_ids") or []
        if iids:
            r = await c.post(f"/projects/{pid}/export", headers=dh, json={
                "image_ids": iids, "formats": ["jpg", "png", "pdf"], "zip": True})
            ok = r.status_code == 200
            if ok:
                jr = r.json()
                ev["export_files"] = [f["filename"] for f in jr.get("files", [])]
                ev["export_pkg"] = jr.get("package_url")
                rec("8.导出(jpg/png/pdf+zip)", len(jr.get("files", [])) >= 3 and jr.get("package_url"),
                    f"HTTP 200 files={ev['export_files']} pkg={ev['export_pkg']}")
            else:
                rec("8.导出", False, f"HTTP {r.status_code} {r.text[:200]}")
        else:
            rec("8.导出", False, "跳过：无可导出图片")

        # ---------- Step 9: 仪表盘 5 维 ----------
        dims = ["overview", "model", "project", "designer", "tier"]
        dim_ok = True
        dim_detail = []
        for d in dims:
            r = await c.get(f"/dashboard/cost?dim={d}", headers=mh)
            body_s = str(r.json())[:90] if r.status_code == 200 else r.text[:80]
            dim_detail.append(f"{d}:HTTP{r.status_code}:{body_s}")
            dim_ok = dim_ok and r.status_code == 200
        rec("9.仪表盘5维", dim_ok, " | ".join(dim_detail))

        # ---------- Step 10: 监控 /metrics ----------
        r = await c.get("/metrics")
        has_prom = r.status_code == 200 and ("# HELP" in r.text or "# TYPE" in r.text)
        rec("10.监控/metrics", has_prom, f"HTTP {r.status_code} body[:80]={r.text[:80]!r}")

        # ---------- Step 5: 异步 + SSE (n=1, Mock seedream, 免费) ----------
        abody = {"customer": "QA花生食品旗舰店", "subscene": "S1", "family": "family_3",
                 "tier": "standard", "style": "清新自然", "category": "食品",
                 "width": 512, "height": 512, "n": 1}
        r = await c.post("/generate/async", headers=gen_headers, json=abody)
        ok = r.status_code == 200
        ajob = r.json().get("job_id") if ok else None
        ev["async_job_id"] = ajob
        if not ajob:
            rec("5.异步入队", False, f"HTTP {r.status_code} {r.text[:150]}")
        else:
            rec("5.异步入队", True, f"HTTP 200 job_id={ajob}")
            events: list[str] = []
            try:
                async with c.stream("GET", f"/generate/{ajob}/events", headers=dh,
                                     timeout=60.0) as s:
                    async for line in s.aiter_lines():
                        if line.startswith("event:"):
                            etype = line.split(":", 1)[1].strip()
                            events.append(etype)
                            if etype in ("task_completed", "task_failed"):
                                break
            except Exception as exc:  # noqa: BLE001 - SSE read timeout/transport
                events.append(f"<stream-error:{exc}>")
            ev["sse_events"] = events
            got_terminal = "task_completed" in events
            got_start = "task_started" in events
            rec("5.SSE事件序列", got_terminal and got_start, f"events={events}")

        with open(EVIDENCE, "w") as f:
            json.dump({"results": results, "evidence": ev}, f, ensure_ascii=False, indent=2)
        npass = sum(1 for x in results if x["ok"])
        print(f"\n==== SUMMARY: {npass}/{len(results)} checks passed ====")
        print(f"evidence -> {EVIDENCE}")


asyncio.run(main())
