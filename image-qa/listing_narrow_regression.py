"""表单收窄轮回归（PRD §3.12.12，commit 067907f）：region/language 收窄 + 新默认真出图 + 旧默认→400。

边界零成本（配不存在 upload：合法 modifier 过 compose→owns 404 / 非法 modifier→400）；
「默认配置真出图」= 新默认全套 1 张真出图 + 视觉核花生卡生效（协调铁律，QA #336/#344）。
用法：QA_BASE=http://localhost:8444 uv run python ../image-qa/listing_narrow_regression.py
"""

import asyncio
import io
import os
from pathlib import Path

import httpx

from qa_auth import login_verified_account
from PIL import Image

BASE = os.environ.get("QA_BASE", "").rstrip("/")
SRC = "/Users/Zhuanz/CLAUDE/image-gen/花生/精修/02aa39d62d25800d3ee14fa91ab42242.jpg"
OUT = Path("/Users/Zhuanz/CLAUDE/image-gen/image-qa/花生提示词AB")
GHOST = "0000000000000000.png"  # 不存在/非自有 → 过 compose 后卡 owns→404
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


def body(uids, platform="淘宝天猫1688", region="中国", language="中文", n=1, category="FOOD"):  # noqa: ANN001
    return {"upload_ids": uids, "prompt": "电商主图：颗粒饱满的花生产品，主体清晰、背景干净、质感突出",
            "ratio": "1:1", "n": n, "category": category,
            "modifiers": {"platform": platform, "region": region, "language": language}}


async def main() -> None:
    if not BASE:
        raise SystemExit("✋ QA_BASE 未设置。")
    print(f"== 表单收窄轮回归 == BASE={BASE}")
    async with httpx.AsyncClient(base_url=BASE, trust_env=False, timeout=600.0) as c:
        session = await login_verified_account(c)
        tok = session.jwt
        H = {"Authorization": f"Bearer {tok}"}

        # ② 旧默认 platform=亚马逊 → 400（修了默认 400 的负例）
        r = await c.post("/listing/generate", headers=H, json=body([GHOST], platform="亚马逊"))
        check("②旧默认 platform=亚马逊→400", r.status_code == 400, f"HTTP {r.status_code} {r.text[:50]}")
        # 4 国内合法 → 404(过校验)
        for p in ("淘宝天猫1688", "拼多多", "京东", "抖音电商"):
            r = await c.post("/listing/generate", headers=H, json=body([GHOST], platform=p))
            check(f"platform {p}→过校验(404)", r.status_code == 404, f"HTTP {r.status_code}")

        # ③ region 收窄 5→1：中国 ok / 其他→400
        r = await c.post("/listing/generate", headers=H, json=body([GHOST], region="中国"))
        check("③region=中国→过校验(404)", r.status_code == 404, f"HTTP {r.status_code}")
        for rg in ("美国", "欧洲", "俄罗斯", "东南亚"):
            r = await c.post("/listing/generate", headers=H, json=body([GHOST], region=rg))
            check(f"③region {rg}→400(已收窄)", r.status_code == 400, f"HTTP {r.status_code}")

        # ④ language 收窄 4→2：中文/英文 ok / 俄语·西语→400
        for lg in ("中文", "英文"):
            r = await c.post("/listing/generate", headers=H, json=body([GHOST], language=lg))
            check(f"④language {lg}→过校验(404)", r.status_code == 404, f"HTTP {r.status_code}")
        for lg in ("俄语", "西语"):
            r = await c.post("/listing/generate", headers=H, json=body([GHOST], language=lg))
            check(f"④language {lg}→400(已收窄)", r.status_code == 400, f"HTTP {r.status_code}")

        # ⑤ n：n=1 合法、n=7 后端保留 1..7 仍合法（表单固定 1 是纯前端）
        r = await c.post("/listing/generate", headers=H, json=body([GHOST], n=7))
        check("⑤n=7 仍 API 合法(后端留1..7、过校验404)", r.status_code == 404, f"HTTP {r.status_code}")
        r = await c.post("/listing/generate", headers=H, json=body([GHOST], n=8))
        check("⑤n=8→400(后端上限7)", r.status_code == 400, f"HTTP {r.status_code}")

        # ① 新默认全套真出图（默认配置真出图·协调铁律）+ 花生卡生效视觉核
        OUT.mkdir(exist_ok=True)
        uid = (await c.post("/uploads", headers=H, files={"file": ("p.png", to_png(SRC), "image/png")})).json()["id"]
        r = await c.post("/listing/generate", headers=H, json=body([uid]))  # 新默认：淘宝/中国/中文/n=1/FOOD
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
        check("①新默认全套(淘宝/中国/中文/n=1/FOOD)真出图 200", "task_completed" in evs and bool(imgs), f"job={job} {evs}")
        if imgs:
            async with httpx.AsyncClient(trust_env=False, timeout=60.0) as dl:
                resp = await dl.get(imgs[0]["url"])
                (OUT / "收窄-新默认-淘宝中国中文.png").write_bytes(resp.content)
                print(f"① 落盘 收窄-新默认-淘宝中国中文.png ({len(resp.content)//1024} KB) — QA 视觉核花生卡仍生效")

        n = sum(1 for _, x in R if x)
        print(f"\n==== 收窄轮回归: {n}/{len(R)} passed ====（①默认配置真出图图需 QA 视觉核花生卡生效）")


asyncio.run(main())
