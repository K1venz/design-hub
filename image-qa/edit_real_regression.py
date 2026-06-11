"""二次编辑真出图回归（TE-01~04/11/14 + owner，dev f0041fa 终契约）。

命门 = TE-03 链根锚抗累积失真：base 出 1 张 → 拿 image_key 作源 → **连做 3 轮 delta**，
逐轮视觉核产品本体/文字 verbatim、**漂移不随轮数叠加**（每轮锚链根、非上一轮）。
+ TE-02/04 full（构图变、产品+文字锁死）+ owner 越权（他人真实 key→404）+ chain_cost（根算源张单张 R5）
+ R1 联调（根 3 产品图链=4 张喂入）。验收=视觉核标准非像素冻结（PM #654③，生成性细微差异不计 fail）。
⚠️ 需 qa 重建含 f0041fa 后跑。用法：QA_BASE=http://localhost:8444 uv run python ../image-qa/edit_real_regression.py
成本：base+3轮delta+full=¥2.0 + R1(base3+1edit)=¥0.8 ≈ ¥2.8。
"""

import asyncio
import io
import os
import time
from decimal import Decimal
from pathlib import Path

import httpx
from PIL import Image

BASE = os.environ.get("QA_BASE", "").rstrip("/")
SRC = "/Users/Zhuanz/CLAUDE/image-gen/image-qa/通用块多产品/通用块-花生.png"
OUT = Path("/Users/Zhuanz/CLAUDE/image-gen/image-qa/二次编辑回归")
U = (f"qa-edit-r-{int(time.time())}@example.com", "qa-edit-123", "QA编辑真图")
B = (f"qa-edit-b-{int(time.time())}@example.com", "qa-edit-b-123", "QA编辑越权B")
MODS = {"platform": "淘宝天猫1688", "region": "中国", "language": "中文"}


def to_png(path: str) -> bytes:
    img = Image.open(path).convert("RGB")
    s = max(img.size)
    cv = Image.new("RGB", (s, s), (255, 255, 255))
    cv.paste(img, ((s - img.width) // 2, (s - img.height) // 2))
    b = io.BytesIO()
    cv.resize((1024, 1024)).save(b, format="PNG")
    return b.getvalue()


async def token(c, u):  # noqa: ANN001
    r = await c.post("/auth/register", json={"email": u[0], "password": u[1], "name": u[2]})
    if r.status_code != 200:
        r = await c.post("/auth/login", json={"email": u[0], "password": u[1]})
    t = r.json()["jwt"]
    return t, {"Authorization": f"Bearer {t}"}


async def wait_job(c, H, tok, job):  # noqa: ANN001
    try:
        async with c.stream("GET", f"/listing/{job}/events", params={"access_token": tok}) as s:
            ev = None
            async for line in s.aiter_lines():
                if line.startswith("event:"):
                    ev = line.split(":", 1)[1].strip()
                    if ev in ("task_completed", "task_failed"):
                        break
    except httpx.RemoteProtocolError:
        pass  # SSE 断连降级轮询
    for _ in range(120):
        d = (await c.get(f"/listing/jobs/{job}", headers=H)).json()
        if d.get("status") in ("完成", "失败"):
            return d
        await asyncio.sleep(3)
    return (await c.get(f"/listing/jobs/{job}", headers=H)).json()


def key_of(d):  # noqa: ANN001
    imgs = [i for i in d.get("images", []) if i.get("status") == "成功"]
    return (imgs[0].get("image_key"), imgs[0]) if imgs else (None, None)


async def gen(c, H, tok, uploads, n=1):  # noqa: ANN001
    body = {"upload_ids": uploads, "prompt": "电商主图：产品主体清晰、质感真实", "ratio": "1:1",
            "n": n, "category": "FOOD", "modifiers": MODS}
    job = (await c.post("/listing/generate", headers=H, json=body)).json()["job_id"]
    return await wait_job(c, H, tok, job)


async def edit(c, H, tok, source_key, mode, prompt, ratio=None):  # noqa: ANN001
    body = {"source_image_key": source_key, "edit_mode": mode, "prompt": prompt, "modifiers": MODS}
    if ratio is not None:
        body["ratio"] = ratio
    r = await c.post("/listing/edit", headers=H, json=body)
    if r.status_code != 200:
        return r.status_code, None
    return 200, await wait_job(c, H, tok, r.json()["job_id"])


async def dl(c, key_img, fname):  # noqa: ANN001
    if not key_img:
        return
    async with httpx.AsyncClient(trust_env=False, timeout=60.0) as d:
        resp = await d.get(key_img["url"])
        if resp.status_code == 200:
            (OUT / fname).write_bytes(resp.content)


def check(label, ok, extra=""):  # noqa: ANN001
    print(f"  {'PASS' if ok else 'FAIL'}  {label}{('  ' + extra) if extra else ''}")
    return bool(ok)


async def main() -> None:
    if not BASE:
        raise SystemExit("✋ QA_BASE 未设置。")
    OUT.mkdir(exist_ok=True)
    async with httpx.AsyncClient(base_url=BASE, trust_env=False, timeout=900.0) as c:
        tok, H = await token(c, U)
        if (await c.post("/listing/edit", headers=H, json={})).status_code == 404:
            raise SystemExit("⏳ /listing/edit 未上线（ops 未重建 qa 含 f0041fa？）")
        print(f"== 二次编辑真出图回归 (f0041fa) == BASE={BASE}")
        npass = ntotal = 0

        def t(ok):  # noqa: ANN001
            nonlocal npass, ntotal
            ntotal += 1
            npass += ok

        # base（单图 1 upload）
        uid = (await c.post("/uploads", headers=H, files={"file": ("p.png", to_png(SRC), "image/png")})).json()["id"]
        d0 = await gen(c, H, tok, [uid])
        k0, img0 = key_of(d0)
        await dl(c, img0, "0-base.png")
        print(f"\n[base] status={d0.get('status')} image_key={k0}")
        t(check("base 出图 + 有 image_key", bool(k0)))

        # TE-03 三轮 delta 链
        prompts = ["把背景换成纯白", "背景改成浅木色桌面", "整体加一点暖色调光线"]
        ck = k0
        for i, p in enumerate(prompts, 1):
            st, di = await edit(c, H, tok, ck, "delta", p)
            ki, imgi = key_of(di) if di else (None, None)
            await dl(c, imgi, f"{i}-delta轮{i}.png")
            print(f"[delta 轮{i}] http={st} status={di.get('status') if di else '-'} parent={di.get('parent_job_id') if di else '-'} edit_mode={di.get('edit_mode') if di else '-'} image_key={ki}")
            t(check(f"轮{i} 出图 + edit_mode=delta 回显 + parent 链", st == 200 and bool(ki) and di.get("edit_mode") == "delta" and di.get("parent_job_id")))
            t(check(f"轮{i} 复刻张 image_type=null（编辑不引图型卡）", bool(imgi) and imgi.get("image_type") in (None, "")))
            if ki:
                ck = ki
        # chain_cost（根算源张单张 R5）：di=轮3 详情；预期=base源张+3轮=4×单价（值由 dev 聚合口径定，先核 >0 + 落值人工对账）
        cc = di.get("chain_cost") if di else None
        t(check("chain_cost 存在且>0（根算源张单张 R5）", cc is not None and Decimal(str(cc or 0)) > 0, f"chain_cost={cc}（人工对账=base源张+3轮 delta）"))

        # TE-02/04 full（构图变、产品+文字锁死）
        st, df = await edit(c, H, tok, k0, "full", "重做整个画面：温暖木桌生活场景、自然光")
        kf, imgf = key_of(df) if df else (None, None)
        await dl(c, imgf, "5-full.png")
        print(f"[full] http={st} status={df.get('status') if df else '-'} edit_mode={df.get('edit_mode') if df else '-'}")
        t(check("full 出图 + edit_mode=full 回显", st == 200 and bool(kf) and df.get("edit_mode") == "full"))

        # owner 越权：B 编辑 A 的 k0 → 404
        _, HB = await token(c, B)
        rb = await c.post("/listing/edit", headers=HB, json={"source_image_key": k0, "edit_mode": "delta", "prompt": "x", "modifiers": MODS})
        t(check("owner 越权 B 编辑 A 的 key → 404", rb.status_code == 404, f"got {rb.status_code}"))

        # R1：根 3 产品图链 = 4 张喂入
        u3 = [(await c.post("/uploads", headers=H, files={"file": ("p.png", to_png(SRC), "image/png")})).json()["id"] for _ in range(3)]
        d3 = await gen(c, H, tok, u3)
        k3root, _ = key_of(d3)
        if k3root:
            st, dR = await edit(c, H, tok, k3root, "delta", "背景换纯白")
            t(check("R1 根3产品图链 编辑(4张喂入)成功", st == 200 and dR and dR.get("status") == "完成", f"http={st} status={dR.get('status') if dR else '-'}"))
        else:
            t(check("R1 根3产品图 base 出图", False))

        print(f"\n==== 二次编辑真出图 API：{npass}/{ntotal} ====  落盘 → {OUT}")
        print("QA 视觉核：0-base→1→2→3 delta 链逐轮花生袋/文字 verbatim、漂移不累积（非像素冻结）；5-full 构图变产品锁死。")


asyncio.run(main())
