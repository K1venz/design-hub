"""三合一回归（coordinator #246 step5，PRD §3.12.11 / commit 796b32c）：platform 7→4 + category 字段 + 花生卡生效。

边界部分零成本（compose_prompt 在 owns/load 之前校验 platform+category → 配不存在 upload 时：
  非法 platform/category→400；合法→404(过校验、卡在 owns)）。卡生效 1 张真出图(~$0.05)视觉核。
用法：QA_BASE=http://localhost:8444 uv run python ../image-qa/listing_cat_platform_regression.py
"""

import asyncio
import io
import os
from pathlib import Path

import httpx
from PIL import Image

BASE = os.environ.get("QA_BASE", "").rstrip("/")
SRC = "/Users/Zhuanz/CLAUDE/image-gen/花生/精修/02aa39d62d25800d3ee14fa91ab42242.jpg"
OUT = Path("/Users/Zhuanz/CLAUDE/image-gen/image-qa/花生提示词AB")
A = ("qa-cat-reg@example.com", "qa-cat-reg-123", "QA品类回归")
GHOST = "0000000000000000.png"  # 不存在/非自有 upload → 过 compose 后卡在 owns→404
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


def body(uids, platform="抖音电商", category=None, prompt="电商主图：颗粒饱满的花生产品，主体清晰、背景干净、质感突出"):  # noqa: ANN001
    d = {"upload_ids": uids, "prompt": prompt, "ratio": "1:1", "n": 1, "modifiers": {"platform": platform}}
    if category is not None:
        d["category"] = category
    return d


async def main() -> None:
    if not BASE:
        raise SystemExit("✋ QA_BASE 未设置。")
    print(f"== 三合一回归 == BASE={BASE}")
    async with httpx.AsyncClient(base_url=BASE, trust_env=False, timeout=600.0) as c:
        op = await c.get("/openapi.json")
        cat_in_schema = "category" in op.text
        check("0.openapi 含 category 字段(796b32c)", cat_in_schema, f"openapi {op.status_code}")
        r = await c.post("/auth/register", json={"email": A[0], "password": A[1], "name": A[2]})
        if r.status_code != 200:
            r = await c.post("/auth/login", json={"email": A[0], "password": A[1]})
        tok = r.json()["jwt"]
        H = {"Authorization": f"Bearer {tok}"}

        # ① platform 7→4：3 跨境→400（category 给合法 FOOD 隔离 platform）
        for plat in ("亚马逊", "Temu", "TikTok Shop"):
            r = await c.post("/listing/generate", headers=H, json=body([GHOST], platform=plat, category="FOOD"))
            check(f"①跨境 {plat}→400(已删)", r.status_code == 400, f"HTTP {r.status_code} {r.text[:50]}")
        # 4 国内合法 → 过 platform 校验（配不存在 upload → 404，非 400）
        for plat in ("淘宝天猫1688", "拼多多", "京东", "抖音电商"):
            r = await c.post("/listing/generate", headers=H, json=body([GHOST], platform=plat, category="FOOD"))
            check(f"①国内 {plat}→过校验(404 非400)", r.status_code == 404, f"HTTP {r.status_code}")

        # ② category：FOOD 合法 / 未知→400 / 缺省默认 FOOD
        r = await c.post("/listing/generate", headers=H, json=body([GHOST], category="FOOD"))
        check("②category=FOOD 合法→过校验(404)", r.status_code == 404, f"HTTP {r.status_code}")
        r = await c.post("/listing/generate", headers=H, json=body([GHOST], category="BEVERAGE"))
        check("②未知品类 BEVERAGE→400", r.status_code == 400, f"HTTP {r.status_code} {r.text[:50]}")
        r = await c.post("/listing/generate", headers=H, json=body([GHOST], category="不存在"))
        check("②未知品类(中文)→400", r.status_code == 400, f"HTTP {r.status_code}")
        r = await c.post("/listing/generate", headers=H, json=body([GHOST], category=None))  # 不传 category
        check("②缺省 category→默认 FOOD 过校验(404 非400)", r.status_code == 404, f"HTTP {r.status_code}")

        # ③ 花生卡真生效：category=FOOD 真出图 → 下载视觉核（对照优化版基线）
        OUT.mkdir(exist_ok=True)
        uid = (await c.post("/uploads", headers=H, files={"file": ("p.png", to_png(SRC), "image/png")})).json()["id"]
        r = await c.post("/listing/generate", headers=H, json=body([uid], platform="抖音电商", category="FOOD"))
        job = r.json().get("job_id")
        evs = []
        async with c.stream("GET", f"/listing/{job}/events", params={"access_token": tok}) as s:
            async for line in s.aiter_lines():
                if line.startswith("event:"):
                    et = line.split(":", 1)[1].strip()
                    evs.append(et)
                    if et in ("task_completed", "task_failed"):
                        break
        d = (await c.get(f"/listing/jobs/{job}", headers=H)).json()
        imgs = [im for im in d.get("images", []) if im.get("status") == "成功"]
        check("③category=FOOD 真出图成功", "task_completed" in evs and bool(imgs), f"job={job} {evs}")
        if imgs:
            async with httpx.AsyncClient(trust_env=False, timeout=60.0) as dl:
                resp = await dl.get(imgs[0]["url"])
                (OUT / "卡生效-category=FOOD-抖音.png").write_bytes(resp.content)
                print(f"③ 落盘 卡生效-category=FOOD-抖音.png ({len(resp.content)//1024} KB) — QA 视觉核保真块效果(对照优化版基线)")

        n = sum(1 for _, ok in R if ok)
        print(f"\n==== 三合一回归: {n}/{len(R)} passed ====（③卡生效图需 QA 视觉核：饱满真实不圆+包装绝对保真）")


asyncio.run(main())
