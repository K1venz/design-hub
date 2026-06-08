"""ISSUE-0030 持久化+历史 e2e（真 MySQL + 真 gpt-image，n=1 控成本）。

2 用户(A/B)、真实出图(重试到成功，失败不计费)、列表/详情、**越权隔离(A token 取 B 的 job→404)**、图 url 直 GET。
cd image-code && uv run python ../image-qa/listing_history_e2e.py
"""

import asyncio
import io
import json
import os
import time

import httpx
from PIL import Image

BASE = os.environ.get("QA_BASE", "http://127.0.0.1:8002")  # server qa 实例经隧道时设 QA_BASE
SRC = "/Users/Zhuanz/CLAUDE/image-gen/花生/精修/02aa39d62d25800d3ee14fa91ab42242.jpg"
A = ("qa-hist-a@test.com", "qa-hist-a-123", "用户A")
B = ("qa-hist-b@test.com", "qa-hist-b-123", "用户B")

R: list[tuple[str, bool]] = []


def check(name: str, cond: bool, detail: str = "") -> None:
    R.append((name, bool(cond)))
    print(f"[{'PASS' if cond else 'FAIL'}] {name} {detail}")


def to_png(path: str, side: int = 1024) -> bytes:
    img = Image.open(path).convert("RGB")
    s = max(img.size)
    cv = Image.new("RGB", (s, s), (255, 255, 255))
    cv.paste(img, ((s - img.width) // 2, (s - img.height) // 2))
    b = io.BytesIO()
    cv.resize((side, side)).save(b, format="PNG")
    return b.getvalue()


async def tok(c: httpx.AsyncClient, email: str, pw: str, name: str) -> str:
    r = await c.post("/auth/register", json={"email": email, "password": pw, "name": name})
    if r.status_code != 200:
        r = await c.post("/auth/login", json={"email": email, "password": pw})
    return r.json()["jwt"]


async def wait_sse(c: httpx.AsyncClient, ta: str, job: str) -> list[str]:
    evs: list[str] = []
    async with c.stream("GET", f"/listing/{job}/events", params={"access_token": ta}) as s:
        async for line in s.aiter_lines():
            if line.startswith("event:"):
                et = line.split(":", 1)[1].strip()
                evs.append(et)
                if et in ("task_completed", "task_failed"):
                    break
    return evs


async def main() -> None:
    async with httpx.AsyncClient(base_url=BASE, trust_env=False, timeout=600.0) as c:
        ta = await tok(c, *A)
        tb = await tok(c, *B)
        Ha = {"Authorization": f"Bearer {ta}"}
        Hb = {"Authorization": f"Bearer {tb}"}
        uid = (await c.post("/uploads", headers=Ha, files={"file": ("p.png", to_png(SRC), "image/png")})).json()["id"]
        print(f"[setup] A upload_id={uid}")

        # 真实出图：重试到成功（失败=中转站抽风，已回滚不计费；只有成功计 ¥1.19）
        body = {"upload_ids": [uid], "prompt": "中国风年货花生电商主图，颗粒饱满主体清晰",
                "ratio": "1:1", "n": 1, "modifiers": {"platform": "亚马逊", "region": "美国", "language": "英文"}}
        job = ""
        ok = False
        for attempt in range(1, 4):
            r = await c.post("/listing/generate", headers=Ha, json=body)
            job = r.json()["job_id"]
            t0 = time.perf_counter()
            evs = await wait_sse(c, ta, job)
            dt = int(time.perf_counter() - t0)
            print(f"[gen] 第{attempt}次 job={job} {dt}s {evs}")
            if "task_completed" in evs:
                ok = True
                break
            print(f"[gen] 第{attempt}次失败(中转站)，重试…")
        check("1.真实出图成功(完成)", ok, f"job={job}（{attempt} 次内成功）")
        print(f"JOB_A={job} UID_A={uid} OK={ok}")

        # 2. 列表(A)
        r = await c.get("/listing/jobs", headers=Ha)
        jobs = r.json() if r.status_code == 200 else []
        item = next((j for j in jobs if j["job_id"] == job), None)
        exp_status = "完成" if ok else "失败"
        check("2.列表含本人 job + 字段齐", item is not None and item["status"] == exp_status
              and item["ratio"] == "1:1" and item["n"] == 1 and "total_cost" in item
              and "platform" in item and "created_at" in item, f"{item}")
        if ok and item:
            check("2.成功 job: image_count=1 + first_image_url", item["image_count"] == 1 and bool(item["first_image_url"]), f"{item}")
        for q, code, tag in [("limit=0", 400, "limit=0"), ("limit=101", 400, "limit=101"),
                             ("offset=-1", 400, "offset=-1"), ("limit=20&offset=0", 200, "正常")]:
            rr = await c.get(f"/listing/jobs?{q}", headers=Ha)
            check(f"2.分页参数 {tag}→{code}", rr.status_code == code, f"HTTP {rr.status_code}")

        # 3. 详情(A)
        r = await c.get(f"/listing/jobs/{job}", headers=Ha)
        d = r.json() if r.status_code == 200 else {}
        meta_ok = (r.status_code == 200 and d.get("status") == exp_status and d.get("prompt")
                   and d.get("size") == "1024x1024" and len(d.get("input_urls", [])) == 1)
        check("3.详情元数据+输入图齐", meta_ok, f"status={d.get('status')} inputs={len(d.get('input_urls',[]))}")
        out_url = ""
        if ok:
            imgs = d.get("images", [])
            check("3.成功 job 详情含 1 张候选图", len(imgs) == 1 and imgs[0].get("status") == "成功", f"images={len(imgs)}")
            if imgs:
                out_url = imgs[0].get("url", "")
                check("3.输出图 url 形态 /img/<key>.png", "/img/" in out_url and out_url.endswith(".png"), out_url)
        in_url = (d.get("input_urls") or [""])[0]

        # 4. 权限隔离（重点）
        r = await c.get(f"/listing/jobs/{job}", headers=Hb)
        check("4.越权 B 取 A 的 job→404(不泄露)", r.status_code == 404, f"HTTP {r.status_code}")
        r = await c.get("/listing/jobs/nonexistentjobid", headers=Ha)
        check("4.不存在 job→404", r.status_code == 404, f"HTTP {r.status_code}")
        r = await c.get("/listing/jobs")
        check("4.无Bearer 列表→401", r.status_code == 401, f"HTTP {r.status_code}")
        r = await c.get(f"/listing/jobs/{job}")
        check("4.无Bearer 详情→401", r.status_code == 401, f"HTTP {r.status_code}")
        r = await c.get("/listing/jobs", headers=Hb)
        check("4.B 列表不含 A 的 job", all(j["job_id"] != job for j in r.json()), f"B jobs={len(r.json())}")

        # 5. 图 url 直 GET（独立 client）
        async with httpx.AsyncClient(trust_env=False, timeout=20.0) as c2:
            if out_url:
                ro = await c2.get(out_url)
                check("5.输出图 url GET→200 image/*", ro.status_code == 200
                      and ro.headers.get("content-type", "").startswith("image/"),
                      f"HTTP {ro.status_code} ct={ro.headers.get('content-type')} {out_url}")
            if in_url:
                ri = await c2.get(in_url)
                check("5.输入图 url GET→200 image/*", ri.status_code == 200
                      and ri.headers.get("content-type", "").startswith("image/"),
                      f"HTTP {ri.status_code} {in_url}（404=输入图落 assets/ 但 url 指 /img/(generated) 不一致）")

        with open("/tmp/listing30-ev.json", "w") as f:
            json.dump({"job": job, "uid": uid, "ok": ok, "out_url": out_url, "in_url": in_url}, f)
        n = sum(1 for _, x in R if x)
        print(f"\n==== ISSUE-0030 历史 e2e: {n}/{len(R)} passed ====  job={job} success={ok}")


asyncio.run(main())
