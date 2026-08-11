"""花生第一轮真实出图（图生图 EDIT）。

用「花生/精修」里的真实产品图作产品素材 → 项目第一轮出图（n=1）→ 真实 gpt-image-2 /images/edits。
这是真实调用（成本~¥0.1-0.4，edit 端点可能 ~187s 或撞中转站 500 触发重试，见 ISSUE-0007）。
"""

import asyncio
import io
import sys
import time

import httpx

from qa_auth import login_verified_account
from PIL import Image

BASE = "http://127.0.0.1:8000"
SRC = "/Users/Zhuanz/CLAUDE/image-gen/花生/精修/02aa39d62d25800d3ee14fa91ab42242.jpg"
TARGET_PROJECT = int(sys.argv[1]) if len(sys.argv) > 1 else None


def to_square_png(path: str, side: int = 1024) -> bytes:
    """产品图 → 居中留白方图 PNG（gpt-image edit 偏好方形 PNG；避免拉伸变形）。"""
    img = Image.open(path).convert("RGB")
    s = max(img.size)
    canvas = Image.new("RGB", (s, s), (255, 255, 255))
    canvas.paste(img, ((s - img.width) // 2, (s - img.height) // 2))
    canvas = canvas.resize((side, side))
    buf = io.BytesIO()
    canvas.save(buf, format="PNG")
    return buf.getvalue()


async def main() -> None:
    async with httpx.AsyncClient(base_url=BASE, trust_env=False, timeout=600.0) as c:
        session = await login_verified_account(c)
        jwt = session.jwt
        h = {"Authorization": f"Bearer {jwt}"}
        gh = {**h, "X-User-Id": "qa-designer-001"}

        if TARGET_PROJECT is not None:
            pid = TARGET_PROJECT
            print(f"[setup] 挂到已有项目 project={pid}（不新建）")
        else:
            cid = (await c.post("/customers", headers=h, json={
                "name": "嘴嘴熊食品", "industry": "食品", "common_styles": ["清新自然"]})).json()["id"]
            pid = (await c.post("/projects", headers=h, json={
                "customer_id": cid, "name": "嘴嘴熊高山七彩花生-主图"})).json()["id"]
        await c.put(f"/projects/{pid}/brief", headers=h, json={
            "material_types": ["主图"], "sizes": ["1024x1024"], "styles": ["清新自然"],
            "resolution": "300dpi", "bleed": "0", "copy_text": "嘴嘴熊 高山七彩花生 66g",
            "taboo": "不夸大功效", "delivery": {"format": "jpg"}})
        png = to_square_png(SRC)
        aid = (await c.post(f"/projects/{pid}/assets", headers=h, data={"kind": "产品图"},
                            files={"file": ("peanut.png", png, "image/png")})).json()["id"]
        print(f"[setup] project={pid} asset={aid}（产品图 {len(png)//1024}KB PNG）")

        body = {"subscene": "S1", "family": "family_4", "category": "食品", "tier": "standard",
                "style": "清新自然", "width": 1024, "height": 1024, "n": 1, "asset_ids": [aid]}
        print("[generate] 第一轮 图生图 EDIT 真实出图中…（edit 端点慢，可能 ~187s）")
        t0 = time.perf_counter()
        r = await c.post(f"/projects/{pid}/generate", headers=gh, json=body)
        dt = int((time.perf_counter() - t0) * 1000)
        print(f"[generate] HTTP {r.status_code} latency={dt}ms")
        if r.status_code != 200:
            print(f"[generate] 失败 body={r.text[:400]}")
            print(f"[hint] 若 502 provider_failed=中转站 edit 端点过载/超时(ISSUE-0007 半②外部问题)")
            return
        j = r.json()
        url = (j.get("images") or [{}])[0].get("url", "")
        print(f"[generate] used_model={j['used_model']} job_id={j['job_id']} round_no={j['round_no']} "
              f"cost={j['total_cost']}")
        print(f"[generate] 出图 url={url}")
        print(f"[result] project_id={pid} 第一轮已落库；前端「任务与选稿」应能看到此 job 的花生候选图")


asyncio.run(main())
