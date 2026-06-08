"""花生真实感 B（加强版，coordinator #191）：精修参考 + 纯实拍花生 DSC 第二参考 + 保真块。

同场景同比例(亚马逊/1:1)，只比 A/B 的"新"多喂一张实拍花生 DSC → 看真实感能否再上一台阶。
落盘 image-qa/花生提示词AB/亚马逊-1x1-B-双参考.png，与旧/新组成三连。qa n=1 ≈ $0.05。
用法：QA_BASE=http://localhost:8444 uv run python ../image-qa/listing_peanut_ab_b.py
"""

import asyncio
import io
import os
import time
from pathlib import Path

import httpx
from PIL import Image

BASE = os.environ.get("QA_BASE", "").rstrip("/")
SRC1 = "/Users/Zhuanz/CLAUDE/image-gen/花生/精修/02aa39d62d25800d3ee14fa91ab42242.jpg"  # 精修成品图
SRC2 = "/Users/Zhuanz/CLAUDE/image-gen/花生/休闲/DSC_5931.JPG"  # 纯实拍带壳花生(真质感)
OUT = Path("/Users/Zhuanz/CLAUDE/image-gen/image-qa/花生提示词AB")
A = ("qa-acc-a@example.com", "qa-acc-a-123", "验收用户A")

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
        uid1 = (await c.post("/uploads", headers=H, files={"file": ("p1.png", to_png(SRC1), "image/png")})).json()["id"]
        uid2 = (await c.post("/uploads", headers=H, files={"file": ("p2.png", to_png(SRC2), "image/png")})).json()["id"]
        print(f"[B] 双参考上传：精修={uid1} 实拍={uid2}")
        body = {"upload_ids": [uid1, uid2], "prompt": FIDELITY + "\n" + SCENE, "ratio": "1:1", "n": 1, "modifiers": MODIFIERS}
        for attempt in range(1, 3):
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
            print(f"[B] 第{attempt}次 job={job} {int(time.perf_counter()-t0)}s {evs}")
            if "task_completed" in evs:
                break
        d = (await c.get(f"/listing/jobs/{job}", headers=H)).json()
        imgs = [im for im in d.get("images", []) if im.get("status") == "成功"]
        if imgs:
            async with httpx.AsyncClient(trust_env=False, timeout=60.0) as dl:
                resp = await dl.get(imgs[0]["url"])
                (OUT / "亚马逊-1x1-B-双参考(精修+实拍).png").write_bytes(resp.content)
                print(f"[B] 落盘 亚马逊-1x1-B-双参考(精修+实拍).png ({len(resp.content)//1024} KB)")
        # 三连 index
        (OUT / "index.md").write_text(
            "# 花生真实感提示词 实验 · 三连（coordinator #182/#191）\n\n"
            "唯一变量见各列；同场景卖点 + 同比例 1:1 + 同平台亚马逊/英文。\n\n"
            "| 文件 | 参考图 | prompt | 说明 |\n|---|---|---|---|\n"
            "| 亚马逊-1x1-旧-原prompt.png | 精修成品图×1 | 原「电商主图…」 | 旧：花生塑料/规整、且模型把真包装换成伪英文假袋 |\n"
            "| 亚马逊-1x1-新-加保真块.png | 精修成品图×1 | 保真块+原场景 | 新：花生更哑光真实 + 保留原版嘴嘴熊中文袋(逐字)；去了卖点文字层 |\n"
            "| 亚马逊-1x1-B-双参考(精修+实拍).png | 精修×1 + **实拍带壳花生 DSC_5931×1** | 保真块+原场景 | B：在新基础上多喂一张纯实拍花生，看真实感再上台阶 |\n\n"
            "> 参考：精修图=嘴嘴熊袋+真实拍紫花生+场景；DSC_5931=休闲场景纯实拍带壳花生(真网状脉络土黄壳)。\n"
        )
        print(f"\n==== B 落盘 → {OUT} ====")


asyncio.run(main())
