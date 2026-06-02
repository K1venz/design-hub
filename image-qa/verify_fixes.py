"""QA re-verification of dev fixes for ISSUE-0008 / 0009 / 0010 (all zero real-image cost).

- 0008 /metrics: prometheus endpoint + business counters increment after a mock generation.
- 0010 SSE replay: late subscribe (delay 1.5s) still replays task_started..task_completed (Redis Stream).
- 0009 ledger reconcile: bogus GPT (:8001) forces fallback -> seedream(0.20); ledger net must equal actual,
  not the GPT reservation (1.19). (DB net checked separately via mysql.)

All generations route to Mock seedream (family_3) or fail-fast bogus GPT -> Mock fallback. No real gpt-image.
"""

import asyncio

import httpx

MAIN = "http://127.0.0.1:8000"
BOGUS = "http://127.0.0.1:8001"


async def token(base: str) -> str:
    async with httpx.AsyncClient(base_url=base, trust_env=False, timeout=30.0) as c:
        return (await c.post("/auth/feishu/callback", json={"code": "designer-verify"})).json()["jwt"]


async def verify_0008(c: httpx.AsyncClient, h: dict) -> None:
    print("\n========== ISSUE-0008 /metrics ==========")
    r = await c.get("/metrics")
    has_prom = r.status_code == 200 and ("# HELP" in r.text or "# TYPE" in r.text)
    print(f"[0008] GET /metrics -> HTTP {r.status_code}, prometheus_format={has_prom}")

    # mock 同步出图 (family_3 standard -> seedream, 0 成本) 触发业务埋点
    body = {"customer": "QA验证", "subscene": "S1", "family": "family_3", "tier": "standard",
            "style": "清新自然", "category": "食品", "width": 512, "height": 512, "n": 1}
    g = await c.post("/generate", headers=h, json=body)
    print(f"[0008] mock 出图 -> HTTP {g.status_code} used_model={g.json().get('used_model') if g.status_code==200 else g.text[:80]}")

    r2 = await c.get("/metrics")
    lines = [ln for ln in r2.text.splitlines()
             if ln.startswith("design_hub_") and "generation" in ln.lower() or
             (ln.startswith("design_hub_") and "image" in ln.lower())]
    biz = [ln for ln in r2.text.splitlines() if ln.startswith("design_hub_") and not ln.startswith("#")]
    print(f"[0008] /metrics 业务指标样本（design_hub_*）：")
    for ln in biz[:12]:
        print(f"        {ln}")
    gen_total = [ln for ln in biz if "generations_total" in ln]
    ok = has_prom and bool(gen_total)
    print(f"[0008] RESULT = {'PASS' if ok else 'FAIL'} (prometheus + design_hub_generations_total present)")


async def verify_0010(c: httpx.AsyncClient, h: dict) -> None:
    print("\n========== ISSUE-0010 SSE 晚订阅回放 ==========")
    body = {"customer": "QA验证", "subscene": "S1", "family": "family_3", "tier": "standard",
            "style": "清新自然", "category": "食品", "width": 512, "height": 512, "n": 1}
    r = await c.post("/generate/async", headers=h, json=body)
    job_id = r.json()["job_id"]
    print(f"[0010] 入队 job_id={job_id}；故意延迟 1.5s 再订阅（旧 pub/sub 此时已丢 task_started）")
    await asyncio.sleep(1.5)  # 让 worker 处理完并 XADD 全部事件

    events: list[str] = []
    try:
        async with c.stream("GET", f"/generate/{job_id}/events", headers=h, timeout=30.0) as s:
            async for line in s.aiter_lines():
                if line.startswith("event:"):
                    et = line.split(":", 1)[1].strip()
                    events.append(et)
                    if et in ("task_completed", "task_failed"):
                        break
    except Exception as exc:  # noqa: BLE001
        events.append(f"<err:{exc}>")
    ok = "task_started" in events and "task_completed" in events
    print(f"[0010] 晚订阅收到事件：{events}")
    print(f"[0010] RESULT = {'PASS' if ok else 'FAIL'} (含 task_started 全序列回放)")


async def verify_0009() -> None:
    print("\n========== ISSUE-0009 fallback 后 ledger 回正 (bogus GPT :8001) ==========")
    jwt = await token(BOGUS)
    h = {"Authorization": f"Bearer {jwt}", "X-User-Id": "recon-001"}
    async with httpx.AsyncClient(base_url=BOGUS, trust_env=False, timeout=60.0) as c:
        # text2img family_4 -> 主 GPT(bogus, 连接失败) -> fallback seedream(0.20)
        body = {"customer": "QA验证", "subscene": "S1", "family": "family_4", "tier": "standard",
                "style": "清新自然", "category": "食品", "width": 512, "height": 512, "n": 1}
        g = await c.post("/generate", headers=h, json=body)
        if g.status_code != 200:
            print(f"[0009] 出图 HTTP {g.status_code} {g.text[:200]} -> 期望 fallback 成功，FAIL"); return
        j = g.json()
        fell_back = j["used_model"] == "seedream-5"
        print(f"[0009] 出图 HTTP 200 used_model={j['used_model']} total_cost={j['total_cost']} (主GPT失败→fallback={fell_back})")
        print(f"[0009] 预扣应=GPT估(1.19)，实际=seedream(0.20)；ledger 净额应回正到 0.20（DB 复核见下）")


async def main() -> None:
    jwt = await token(MAIN)
    h = {"Authorization": f"Bearer {jwt}"}
    async with httpx.AsyncClient(base_url=MAIN, trust_env=False, timeout=60.0) as c:
        await verify_0008(c, h)
        await verify_0010(c, h)
    await verify_0009()


asyncio.run(main())
