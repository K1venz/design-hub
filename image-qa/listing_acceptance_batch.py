"""ISSUE-0035 真实并发 + F1/F2 批量采样 + 预算硬顶（server qa 实例专用）。

补现有 n=1 脚本（listing_history_e2e.py）覆盖不到的：
- A4  : n=3/5/7 各一次 —— 真实并发、N 候选齐、部分失败→部分完成、per-image seed/cost
- F1  : 多组 n=1 happy 凑样本 —— 完成率作客观代理（视觉「可用率」需人工/PM 评分，本脚本存图 url 供评）
- F2  : 复用全部 job 端到端时延算 P95（目标 ≤5min，N≤7）
- E1  : 每个 job 聚合 total_cost==Σ(image cost) 核预扣→回正
- D1  : B 取 A 的 job → 404（不泄露存在性）

★ 双轴隔离前提：QA_BASE 必须指 server qa 实例（独立 design_hub_qa 库 + qa 专用 TOS 桶），绝不指 prod。
★ 预算硬顶：累计真实出图张数到 QA_MAX_IMAGES（默认 50，守 60 红线留 buffer）即停。

两阶段防误刷成本：
  # 阶段0 干跑：只 register+upload，打印存储落点（自查/问 ops 确认是 qa 桶非 prod 后再真跑）
  QA_BASE=http://127.0.0.1:8444 uv run python ../image-qa/listing_acceptance_batch.py
  # 阶段1 真跑：确认存储落点后
  QA_BASE=http://127.0.0.1:8444 QA_CONFIRM_COSTED=1 uv run python ../image-qa/listing_acceptance_batch.py
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
COSTED = os.environ.get("QA_CONFIRM_COSTED") == "1"
MAX_IMAGES = int(os.environ.get("QA_MAX_IMAGES", "50"))
SRC = os.environ.get(
    "QA_SRC", "/Users/Zhuanz/CLAUDE/image-gen/花生/精修/02aa39d62d25800d3ee14fa91ab42242.jpg"
)
A = ("qa-acc-a@test.local", "qa-acc-a-123", "验收用户A")
B = ("qa-acc-b@test.local", "qa-acc-b-123", "验收用户B")

# F1 happy 采样：覆盖几个平台×比例组合（n=1），凑可用率样本
HAPPY_MATRIX = [
    {"ratio": "1:1", "modifiers": {"platform": "亚马逊", "region": "美国", "language": "英文"}},
    {"ratio": "3:4", "modifiers": {"platform": "淘宝天猫1688", "region": "中国", "language": "中文"}},
    {"ratio": "16:9", "modifiers": {"platform": "Temu", "region": "欧洲", "language": "英文"}},
    {"ratio": "9:16", "modifiers": {"platform": "TikTok Shop", "region": "东南亚", "language": "英文"}},
    {"ratio": "1:1", "modifiers": {"platform": "拼多多", "region": "中国", "language": "中文"}},
]
PROMPT = "电商主图：颗粒饱满的花生产品，主体清晰、背景干净、质感突出"


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


async def wait_sse(c: httpx.AsyncClient, token: str, job: str) -> tuple[list[str], float]:
    evs: list[str] = []
    t0 = time.perf_counter()
    async with c.stream("GET", f"/listing/{job}/events", params={"access_token": token}) as s:
        async for line in s.aiter_lines():
            if line.startswith("event:"):
                et = line.split(":", 1)[1].strip()
                evs.append(et)
                if et in ("task_completed", "task_failed"):
                    break
    return evs, time.perf_counter() - t0


async def run_job(
    c: httpx.AsyncClient, token: str, headers: dict, uid: str, n: int, ratio: str,
    modifiers: dict, retries: int = 1,
) -> dict:
    """跑一个 listing job，返回完整结果（含 SSE 事件、时延、落库详情）。失败重试（失败不计费）。"""
    body = {"upload_ids": [uid], "prompt": PROMPT, "ratio": ratio, "n": n, "modifiers": modifiers}
    for attempt in range(1, retries + 2):
        r = await c.post("/listing/generate", headers=headers, json=body)
        if r.status_code != 200:
            return {"ok": False, "http": r.status_code, "body": r.text[:200], "n": n, "ratio": ratio}
        job = r.json()["job_id"]
        evs, dt = await wait_sse(c, token, job)
        d = (await c.get(f"/listing/jobs/{job}", headers=headers)).json()
        completed = "task_completed" in evs
        result = {
            "ok": completed, "job": job, "n": n, "ratio": ratio, "attempt": attempt,
            "latency_s": round(dt, 1), "events": evs, "status": d.get("status"),
            "size": d.get("size"), "total_cost": d.get("total_cost"),
            "images": d.get("images", []), "input_urls": d.get("input_urls", []),
            "error": d.get("error"),
        }
        if completed:
            return result
        if attempt <= retries:
            print(f"    job {job} 未完成({d.get('status')})，重试 {attempt}/{retries}…")
    return result


def p95(values: list[float]) -> float:
    if not values:
        return 0.0
    xs = sorted(values)
    idx = min(len(xs) - 1, int(round(0.95 * (len(xs) - 1))))
    return xs[idx]


async def main() -> None:
    if not BASE:
        raise SystemExit("✋ QA_BASE 未设置——必须显式指向 server qa 实例（独立库+qa TOS 桶），拒绝默认值以防误打 prod。")
    print(f"== ISSUE-0035 批量验收 == BASE={BASE} costed={COSTED} max_images={MAX_IMAGES}")

    async with httpx.AsyncClient(base_url=BASE, trust_env=False, timeout=600.0) as c:
        ta = await tok(c, *A)
        tb = await tok(c, *B)
        Ha = {"Authorization": f"Bearer {ta}"}
        Hb = {"Authorization": f"Bearer {tb}"}

        up = await c.post("/uploads", headers=Ha, files={"file": ("p.png", to_png(SRC), "image/png")})
        uid = up.json()["id"]
        preview = (await c.get(f"/uploads/{uid}", params={"access_token": ta}))
        print("\n--- 存储落点自查闸（出图前必看，确认是 qa 桶不是 prod 桶）---")
        print(f"  upload id      : {uid}")
        print(f"  upload url     : {up.json()['url']}")
        print(f"  preview GET    : HTTP {preview.status_code} ct={preview.headers.get('content-type')}")

        if not COSTED:
            total_imgs = len(HAPPY_MATRIX) * 1 + (3 + 5 + 7)
            print(f"\n[干跑] 未设 QA_CONFIRM_COSTED=1，不触发真实出图。")
            print(f"[计划] F1/A3 happy {len(HAPPY_MATRIX)} 组 n=1 + A4 n=3/5/7 = 约 {total_imgs} 张（硬顶 {MAX_IMAGES}）。")
            print("[下一步] 确认上面 upload url 落点是 qa 桶后，加 QA_CONFIRM_COSTED=1 真跑。")
            return

        results: list[dict] = []
        imgs_used = 0

        async def budget_ok(n: int) -> bool:
            return imgs_used + n <= MAX_IMAGES

        # ---- F1/A3: happy n=1 采样 ----
        print("\n--- F1/A3 happy n=1 采样 ---")
        for i, combo in enumerate(HAPPY_MATRIX, 1):
            if not await budget_ok(1):
                print(f"  预算硬顶 {MAX_IMAGES} 张到顶，停止采样。")
                break
            res = await run_job(c, ta, Ha, uid, 1, combo["ratio"], combo["modifiers"])
            imgs_used += sum(1 for im in res.get("images", []) if im.get("status") == "成功")
            results.append(res)
            print(f"  [{i}] n=1 {combo['ratio']} {combo['modifiers'].get('platform')} → "
                  f"{res.get('status')} {res.get('latency_s')}s cost={res.get('total_cost')} imgs_used={imgs_used}")

        # ---- A4: n=3/5/7 真实并发 ----
        print("\n--- A4 真实并发 n=3/5/7 ---")
        for n in (3, 5, 7):
            if not await budget_ok(n):
                print(f"  预算不足以再跑 n={n}（已用 {imgs_used}/{MAX_IMAGES}），跳过。")
                continue
            res = await run_job(c, ta, Ha, uid, n, "1:1",
                                {"platform": "亚马逊", "region": "美国", "language": "英文"})
            ok_imgs = [im for im in res.get("images", []) if im.get("status") == "成功"]
            imgs_used += len(ok_imgs)
            seeds = {im.get("seed") for im in res.get("images", [])}
            results.append(res)
            print(f"  n={n} → status={res.get('status')} 候选={len(res.get('images', []))} "
                  f"成功={len(ok_imgs)} distinct_seeds={len(seeds)} {res.get('latency_s')}s "
                  f"cost={res.get('total_cost')} imgs_used={imgs_used}")

        # ---- D1: 越权隔离 ----
        last_job = next((r["job"] for r in reversed(results) if r.get("job")), None)
        d1 = None
        if last_job:
            rb = await c.get(f"/listing/jobs/{last_job}", headers=Hb)
            d1 = rb.status_code
            print(f"\n--- D1 越权 --- B 取 A 的 job {last_job} → HTTP {rb.status_code}（期望 404）")

        # ---- 聚合：F1 完成率代理 / F2 P95 / E1 成本 ----
        done = [r for r in results if r.get("ok")]
        lat = [r["latency_s"] for r in results if r.get("latency_s")]
        e1_ok = all(
            Decimal(str(r.get("total_cost") or 0)) == sum(Decimal(str(im.get("cost") or 0)) for im in r.get("images", []))
            for r in done
        )
        summary = {
            "base": BASE, "jobs": len(results), "completed_jobs": len(done),
            "images_used": imgs_used, "completion_rate": round(len(done) / len(results), 3) if results else 0,
            "f2_p95_s": round(p95(lat), 1), "f2_pass": p95(lat) <= 300,
            "e1_cost_consistent": e1_ok, "d1_cross_tenant_http": d1,
            "total_cost": str(sum(Decimal(str(r.get("total_cost") or 0)) for r in done)),
            "image_urls_for_visual_f1": [im.get("url") for r in done for im in r.get("images", [])],
        }
        with open("/tmp/listing35-batch.json", "w") as f:
            json.dump({"summary": summary, "results": results}, f, ensure_ascii=False, indent=2)
        print("\n==== 批量验收汇总 ====")
        print(json.dumps(summary, ensure_ascii=False, indent=2))
        print("\n⚠️ F1 真实「可用率」需对 image_urls_for_visual_f1 做视觉评分（完成率≠可用率）；"
              "完成率仅作客观代理。明细见 /tmp/listing35-batch.json")


asyncio.run(main())
