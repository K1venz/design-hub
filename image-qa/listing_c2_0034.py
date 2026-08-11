"""C2 / ISSUE-0034 验证：generation(海报/项目流) 出 1 张真图 → 写 generated_image。

验法（dev #82 第一种，配合 DB 直查）：
  本脚本出 1 张真图（family_4 真实 gpt，text2img，¥1.19）→ 打印 job + API 返回的图 url（读时现签）。
  随后人工/QA 用只读 DB 查：SELECT url FROM generated_image ORDER BY id DESC LIMIT 5;
  → 应为裸 <sha>.png（存 key 不存签名 url）；不含 ?X-Tos-/http 即 0034 修复生效。
第二验法（TTL=10 真复现）：等 11s 后用同一 API 详情/导出再读图 → 仍 200（读时现签、不吃落库过期）。

用法：QA_BASE=http://localhost:8444 uv run python ../image-qa/listing_c2_0034.py
"""

import asyncio
import io
import os
import time

import httpx

from qa_auth import login_verified_account
from PIL import Image

BASE = os.environ.get("QA_BASE", "").rstrip("/")
def png() -> bytes:
    b = io.BytesIO()
    Image.new("RGB", (768, 768), (210, 180, 140)).save(b, format="PNG")
    return b.getvalue()


async def main() -> None:
    if not BASE:
        raise SystemExit("✋ QA_BASE 必须显式指向 server qa 实例。")
    async with httpx.AsyncClient(base_url=BASE, trust_env=False, timeout=600.0) as c:
        session = await login_verified_account(c)
        jwt = session.jwt
        H = {"Authorization": f"Bearer {jwt}"}

        cid = (await c.post("/customers", headers=H, json={
            "name": "C2花生食品", "contact": "qa@test", "industry": "食品",
            "brand_color": "#C8965A", "common_styles": ["清新自然"], "common_taboos": [], "common_sizes": ["1024x1024"],
        })).json()["id"]
        pid = (await c.post("/projects", headers=H, json={"customer_id": cid, "name": "C2-0034海报验证"})).json()["id"]
        await c.put(f"/projects/{pid}/brief", headers=H, json={
            "material_types": ["主图"], "sizes": ["1024x1024"], "styles": ["清新自然"], "resolution": "300dpi",
            "bleed": "3mm", "copy_text": "坚果年货", "taboo": "不夸大", "delivery": {"format": "jpg"}})
        print(f"[setup] customer={cid} project={pid}")

        # family_4 + standard → 真实 gpt-image（text2img，避开图生图 edit 历史超时风险）
        body = {"subscene": "S1", "family": "family_4", "category": "食品", "tier": "standard",
                "style": "清新自然", "width": 1024, "height": 1024, "n": 1, "asset_ids": []}
        t0 = time.perf_counter()
        r = await c.post(f"/projects/{pid}/generate", headers=H, json=body)
        dt = int(time.perf_counter() - t0)
        print(f"[generate] HTTP {r.status_code} {dt}s")
        if r.status_code != 200:
            print(f"[generate] FAIL body={r.text[:300]}")
            return
        d = r.json()
        job = d.get("job_id")
        url = d.get("url") or d.get("image_url") or ""
        print(f"[generate] used_model={d.get('used_model')} job={job} cost={d.get('cost') or d.get('total_cost')}")
        print(f"[generate] API 返回图 url（读时现签）= {url}")

        # 第二验法：等 11s（>TTL=10）后再读同 job 的图，证明读时现签、不吃落库过期
        if job:
            print("[ttl] 等 11s（>TTL=10）后复读…")
            await asyncio.sleep(11)
            r2 = await c.get(f"/jobs/{job}/images", headers=H)
            imgs = r2.json() if r2.status_code == 200 else []
            print(f"[ttl] /jobs/{job}/images HTTP {r2.status_code} 张数={len(imgs)}")
            if imgs:
                u2 = imgs[0].get("url", "")
                async with httpx.AsyncClient(trust_env=False, timeout=30.0) as c2:
                    ro = await c2.get(u2)
                    print(f"[ttl] 11s 后图 url GET → HTTP {ro.status_code} ct={ro.headers.get('content-type')}")
                    print(f"[ttl] 复读 url = {u2}")
        print("\n→ 下一步：只读 DB 查 generated_image.url 是否裸 key：")
        print("   SELECT id,url FROM generated_image ORDER BY id DESC LIMIT 5;")


asyncio.run(main())
