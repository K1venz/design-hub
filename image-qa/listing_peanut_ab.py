"""花生真实感保真块 A/B（coordinator #182）：同一参考图+同场景+同比例，只把保真块加进 prompt。

"新" = 精修参考 + 亚马逊/1:1 + (保真块 + 原场景prompt)；"旧" = 现有 共评样张/亚马逊-1x1-英文.png(原 prompt)。
落盘 image-qa/花生提示词AB/ 供用户并排看。qa 环境 n=1 ≈ $0.05。
用法：QA_BASE=http://localhost:8444 uv run python ../image-qa/listing_peanut_ab.py
"""

import asyncio
import io
import os
import shutil
import time
from pathlib import Path

import httpx
from PIL import Image

BASE = os.environ.get("QA_BASE", "").rstrip("/")
SRC = "/Users/Zhuanz/CLAUDE/image-gen/花生/精修/02aa39d62d25800d3ee14fa91ab42242.jpg"
OLD = "/Users/Zhuanz/CLAUDE/image-gen/image-qa/共评样张/亚马逊-1x1-英文.png"
OUT = Path("/Users/Zhuanz/CLAUDE/image-gen/image-qa/花生提示词AB")
A = ("qa-acc-a@example.com", "qa-acc-a-123", "验收用户A")

# coordinator #182 的保真块，放在场景/卖点之前
FIDELITY = (
    "保真锁定：严格保留参考产品袋的奶白/浅驼配色、白熊图案、袋面所有文字逐字不变，只重绘周围背景与光线；"
    "严格保留参考实拍花生的真实质感——七彩花生米保持紫罗兰/紫红+奶白大理石纹路本色(不要修成纯色/土黄)、"
    "粒大饱满果实白亮，带壳花生保持土黄硬壳与网状脉络。"
    "真实感：表面整体哑光干爽、仅极轻微自然油润，严禁糖浆高光/油亮反光/塑料光泽；果形自然不规则、有壳尖、"
    "深浅不均、带细褶皱，不要圆润规整的模型感；颗粒大小不一、自然随意散落，允许个别开裂/碎壳/双仁的偶然感，"
    "不要完美整齐排列。"
    "光与镜头：50mm f/2.8 近景浅景深，平视或30°微俯；侧前方自然漫射光勾出凹凸、柔中带方向性硬阴影、"
    "与台面真实接触阴影；前景花生锐利可见脉络、背景虚化。"
    "画面禁止：塑料感、糖浆高光、油亮反光、过度鲜艳饱和、完美整齐排列、人物/水印/多余商品。"
)
SCENE = "电商主图：颗粒饱满的花生产品，主体清晰、背景干净、质感突出"
MODIFIERS = {"platform": "亚马逊", "region": "美国", "language": "英文"}


def to_png(path: str, side: int = 1024) -> bytes:
    img = Image.open(path).convert("RGB")
    s = max(img.size)
    cv = Image.new("RGB", (s, s), (255, 255, 255))
    cv.paste(img, ((s - img.width) // 2, (s - img.height) // 2))
    b = io.BytesIO()
    cv.resize((side, side)).save(b, format="PNG")
    return b.getvalue()


async def main() -> None:
    if not BASE:
        raise SystemExit("✋ QA_BASE 必须指向 server qa 实例。")
    OUT.mkdir(exist_ok=True)
    async with httpx.AsyncClient(base_url=BASE, trust_env=False, timeout=600.0) as c:
        r = await c.post("/auth/register", json={"email": A[0], "password": A[1], "name": A[2]})
        if r.status_code != 200:
            r = await c.post("/auth/login", json={"email": A[0], "password": A[1]})
        tok = r.json()["jwt"]
        H = {"Authorization": f"Bearer {tok}"}
        uid = (await c.post("/uploads", headers=H, files={"file": ("p.png", to_png(SRC), "image/png")})).json()["id"]
        body = {"upload_ids": [uid], "prompt": FIDELITY + "\n" + SCENE, "ratio": "1:1", "n": 1, "modifiers": MODIFIERS}
        t0 = time.perf_counter()
        job = (await c.post("/listing/generate", headers=H, json=body)).json()["job_id"]
        evs = []
        async with c.stream("GET", f"/listing/{job}/events", params={"access_token": tok}) as s:
            async for line in s.aiter_lines():
                if line.startswith("event:"):
                    et = line.split(":", 1)[1].strip()
                    evs.append(et)
                    if et in ("task_completed", "task_failed"):
                        break
        dt = int(time.perf_counter() - t0)
        print(f"[新] job={job} {dt}s {evs}")
        if "task_completed" not in evs:
            print("[新] 出图失败，重试一次…")
            job = (await c.post("/listing/generate", headers=H, json=body)).json()["job_id"]
            async with c.stream("GET", f"/listing/{job}/events", params={"access_token": tok}) as s:
                async for line in s.aiter_lines():
                    if line.startswith("event:"):
                        et = line.split(":", 1)[1].strip()
                        if et in ("task_completed", "task_failed"):
                            print(f"[新] 重试 {et}")
                            break
        d = (await c.get(f"/listing/jobs/{job}", headers=H)).json()
        imgs = [im for im in d.get("images", []) if im.get("status") == "成功"]
        if imgs:
            async with httpx.AsyncClient(trust_env=False, timeout=60.0) as dl:
                resp = await dl.get(imgs[0]["url"])  # fresh signed url
                (OUT / "亚马逊-1x1-新-加保真块.png").write_bytes(resp.content)
                print(f"[新] 落盘 亚马逊-1x1-新-加保真块.png ({len(resp.content)//1024} KB)")
        # 旧（原 prompt，同参考同比例）
        if Path(OLD).exists():
            shutil.copy(OLD, OUT / "亚马逊-1x1-旧-原prompt.png")
            print("[旧] 复制 亚马逊-1x1-旧-原prompt.png")
        (OUT / "index.md").write_text(
            "# 花生真实感提示词 A/B（保真块 · coordinator #182）\n\n"
            "- **唯一变量 = prompt**（同参考图 + 同场景卖点 + 同比例 1:1 + 同平台亚马逊/英文）。\n"
            f"- 参考图：`花生/精修/02aa39….jpg`（已精修成品图：嘴嘴熊包装袋 + 真实实拍紫花生 + 全场景；模型有真花生参考）。\n\n"
            "| 文件 | prompt | 说明 |\n|---|---|---|\n"
            "| 亚马逊-1x1-旧-原prompt.png | 原 = 「电商主图：颗粒饱满的花生产品…」 | 旧：花生偏塑料/规整/亮 |\n"
            "| 亚马逊-1x1-新-加保真块.png | 保真块 + 原场景 | 新：加保真锁定(哑光/不规则/真质感/保留原袋) |\n\n"
            "> ⚠️ 我喂的是 1 张合成成品图、非「袋图+单独实拍花生」2 张；若新图仍不够真，建议喂纯实拍花生(花生/办公|居家|休闲 DSC 原图)当独立参考。\n"
        )
        print(f"\n==== A/B 落盘 → {OUT} ====")


asyncio.run(main())
