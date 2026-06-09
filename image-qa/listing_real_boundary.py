"""listing 两步流边界/契约用例 —— 全部打真服务器 :8002（真路由+真 provider+真鉴权），无 mock。

非法入参在路由边界 fail-fast（400/401/404），不触发真实出图 → 零成本。
happy 路径（真实出图）见 listing_real_e2e.py 的 C/D。
cd image-code && uv run python ../image-qa/listing_real_boundary.py
"""

import asyncio
import os

import httpx

BASE = os.environ.get("QA_BASE", "http://127.0.0.1:8002")  # server qa 实例经隧道时设 QA_BASE
DESIGNER = ("qa-designer@test.com", "qa-designer-12345")
PNG = b"\x89PNG\r\n\x1a\n" + b"qa-real-boundary" * 4  # 合法 content-type 即可，上传不校验图像可解码

R: list[tuple[str, bool]] = []


def check(name: str, cond: bool, detail: str = "") -> None:
    R.append((name, bool(cond)))
    print(f"[{'PASS' if cond else 'FAIL'}] {name} {detail}")


def body(upload_ids, prompt="纯白背景突出产品", ratio="1:1", n=2, modifiers=None):  # noqa: ANN001
    # 默认平台用国内合法值（platform 收窄 7→4 后亚马逊已非法，PRD §3.12.2）
    return {"upload_ids": upload_ids, "prompt": prompt, "ratio": ratio, "n": n,
            "modifiers": modifiers if modifiers is not None else {"platform": "抖音电商"}}


async def main() -> None:
    async with httpx.AsyncClient(base_url=BASE, trust_env=False, timeout=30.0) as c:
        r = await c.post("/auth/register", json={"email": DESIGNER[0], "password": DESIGNER[1], "name": "QA设计师"})
        if r.status_code != 200:
            r = await c.post("/auth/login", json={"email": DESIGNER[0], "password": DESIGNER[1]})
        token = r.json()["jwt"]
        H = {"Authorization": f"Bearer {token}"}

        # ---------- A. 上传端点（真服务器）----------
        r = await c.post("/uploads", headers=H, files={"file": ("a.png", PNG, "image/png")})
        uid = r.json().get("id") if r.status_code == 200 else None
        check("A1.合法上传→200{id,url}", r.status_code == 200 and r.json().get("url") == f"/uploads/{uid}", f"HTTP {r.status_code} {r.json() if r.status_code==200 else r.text[:80]}")
        r = await c.post("/uploads", headers=H, files={"file": ("big.png", b"\x00" * (11 * 1024 * 1024), "image/png")})
        check("A2.>10MB→400", r.status_code == 400, f"HTTP {r.status_code} {r.text[:60]}")
        r = await c.post("/uploads", headers=H, files={"file": ("x.gif", PNG, "image/gif")})
        check("A3.非白名单(gif)→400", r.status_code == 400, f"HTTP {r.status_code}")
        r = await c.post("/uploads", headers=H, files={"file": ("e.png", b"", "image/png")})
        check("A4.空文件→400", r.status_code == 400, f"HTTP {r.status_code}")
        r = await c.post("/uploads", files={"file": ("a.png", PNG, "image/png")})
        check("A5.无Bearer→401", r.status_code == 401, f"HTTP {r.status_code}")
        r = await c.get(f"/uploads/{uid}", params={"access_token": token})
        check("A6.预览→200 image/*", r.status_code == 200 and r.headers.get("content-type", "").startswith("image/"), f"HTTP {r.status_code} ct={r.headers.get('content-type')}")
        r = await c.get(f"/uploads/{uid}")
        check("A7.预览无access_token→401", r.status_code == 401, f"HTTP {r.status_code}")
        r = await c.get("/uploads/0000000000000000.png", params={"access_token": token})
        check("A8.缺失id→404", r.status_code == 404, f"HTTP {r.status_code}")
        r = await c.get("/uploads/badid", params={"access_token": token})
        check("A9.非法id格式→404(防枚举,0032/797ca06)", r.status_code == 404, f"HTTP {r.status_code}")

        # ---------- B. 出图入参（真服务器，非法→边界拦截，不出图）----------
        r = await c.post("/listing/generate", headers=H, json=body([]))
        check("B2.upload_ids 0→400", r.status_code == 400, f"HTTP {r.status_code} {r.text[:50]}")
        r = await c.post("/listing/generate", headers=H, json=body([uid] * 4))
        check("B3.upload_ids >3→400", r.status_code == 400, f"HTTP {r.status_code}")
        r = await c.post("/listing/generate", headers=H, json=body(["0000000000000000.png"]))
        check("B4.不存在id→404", r.status_code == 404, f"HTTP {r.status_code} {r.text[:50]}")
        r = await c.post("/listing/generate", headers=H, json=body(["badid"]))
        check("B5.非法id格式→404(防枚举,0032/797ca06)", r.status_code == 404, f"HTTP {r.status_code}")
        r = await c.post("/listing/generate", headers=H, json=body([uid], n=8))
        check("B6.n=8→400(0024)", r.status_code == 400, f"HTTP {r.status_code}")
        r = await c.post("/listing/generate", headers=H, json=body([uid], n=0))
        check("B7.n=0→400", r.status_code == 400, f"HTTP {r.status_code}")
        r = await c.post("/listing/generate", headers=H, json=body([uid], ratio="2:1"))
        check("B8.非法ratio→400(0024)", r.status_code == 400, f"HTTP {r.status_code}")
        r = await c.post("/listing/generate", headers=H, json=body([uid], ratio="4:3"))
        check("B8b.4:3已删→400", r.status_code == 400, f"HTTP {r.status_code}")
        r = await c.post("/listing/generate", headers=H, json=body([uid], prompt="   "))
        check("B9.空prompt→400(0024)", r.status_code == 400, f"HTTP {r.status_code}")
        r = await c.post("/listing/generate", headers=H, json=body([uid], modifiers={"platform": "未知平台"}))
        check("B10.未知下拉→400(0024)", r.status_code == 400, f"HTTP {r.status_code}")
        r = await c.post("/listing/generate", json=body([uid]))
        check("B11.无Bearer→401", r.status_code == 401, f"HTTP {r.status_code}")
        r = await c.get("/listing/none/events")
        check("B11b.SSE无access_token→401", r.status_code == 401, f"HTTP {r.status_code}")

        # ---------- C. 上传归属隔离（ISSUE-0032，listing.py owns() 校验，零成本 fail-fast）----------
        r2 = await c.post("/auth/register", json={"email": "qa-designer2@test.com", "password": "qa-designer2-12345", "name": "QA设计师2"})
        if r2.status_code != 200:
            r2 = await c.post("/auth/login", json={"email": "qa-designer2@test.com", "password": "qa-designer2-12345"})
        token2 = r2.json()["jwt"]
        H2 = {"Authorization": f"Bearer {token2}"}
        uid2 = (await c.post("/uploads", headers=H2, files={"file": ("b.png", PNG, "image/png")})).json().get("id")
        # 用户1(H) 引用用户2(H2) 的 upload_id 出图 → 边界拦截 400（owns 校验失败，不入队、不出图）
        r = await c.post("/listing/generate", headers=H, json=body([uid2]))
        check("C1.引用他人upload_id→404(归属隔离,0032/797ca06)", r.status_code == 404, f"HTTP {r.status_code} {r.text[:60]}")

        n = sum(1 for _, ok in R if ok)
        print(f"\n==== 真服务器边界: {n}/{len(R)} passed（全程真路由真鉴权，无 mock，未出图零成本）====")


asyncio.run(main())
