"""Final real gpt-image attempt (slot 2/2): text2img via /images/generations.

Step-4-real retry through the app pipeline (no asset -> TEXT2IMG -> GPT_IMAGE_2),
then real export (step 8) on the produced file:// image. Reuses project 1.
"""

import asyncio
import time

import httpx

BASE = "http://127.0.0.1:8000"


async def main() -> None:
    async with httpx.AsyncClient(base_url=BASE, trust_env=False, timeout=240.0) as c:
        jwt = (await c.post("/auth/feishu/callback", json={"code": "designer-qa-001"})).json()["jwt"]
        h = {"Authorization": f"Bearer {jwt}", "X-User-Id": "designer-qa-001"}

        body = {"subscene": "S1", "family": "family_4", "category": "食品",
                "tier": "standard", "style": "清新自然", "width": 1024, "height": 1024,
                "n": 1, "asset_ids": []}  # no asset -> text2img -> /images/generations
        t0 = time.perf_counter()
        r = await c.post("/projects/1/generate", headers=h, json=body)
        dt = int((time.perf_counter() - t0) * 1000)
        print(f"[generate] HTTP {r.status_code} latency={dt}ms")
        if r.status_code != 200:
            print(r.text[:400]); return
        j = r.json()
        job_id = j["job_id"]
        url = (j.get("images") or [{}])[0].get("url", "")
        real = j["used_model"] == "gpt-image-2" and url.startswith("file://")
        print(f"[generate] used_model={j['used_model']} job_id={job_id} cost={j['total_cost']} url={url}")
        print(f"[generate] REAL gpt-image success = {real}")

        imgs = (await c.get(f"/jobs/{job_id}/images", headers=h)).json()
        iids = [i["id"] for i in imgs]
        print(f"[images] {iids}")

        if real and iids:
            r = await c.post("/projects/1/export", headers=h,
                             json={"image_ids": iids, "formats": ["jpg", "png", "pdf"], "zip": True})
            print(f"[export] HTTP {r.status_code}")
            if r.status_code == 200:
                jr = r.json()
                print(f"[export] package={jr.get('package_url')}")
                for f in jr.get("files", []):
                    print(f"         - {f['filename']} -> {f['url']}")
            else:
                print(r.text[:400])
        else:
            print("[export] skipped (no real file:// image)")


asyncio.run(main())
