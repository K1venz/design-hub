"""批量跑完后：把完成态 listing job 的输出图字节落盘，供用户本地共评（绕 TTL=10 签名 url 过期）。

GET 详情拿 FRESH 签名 url → 立即下载字节（毫秒级、远在 10s TTL 内）→ 存
  image-qa/共评样张/<平台>-<比例>-<语言>[-序号].png + index.md（元数据表）。
用法：QA_BASE=http://localhost:8444 uv run python ../image-qa/save_samples.py
"""

import asyncio
import os
import re
from pathlib import Path

import httpx

BASE = os.environ.get("QA_BASE", "").rstrip("/")
A = ("qa-acc-a@example.com", "qa-acc-a-123")
OUT = Path("/Users/Zhuanz/CLAUDE/image-gen/image-qa/共评样张")


def safe(s: str) -> str:
    return re.sub(r"[^\w一-鿿.-]", "_", s)


async def main() -> None:
    if not BASE:
        raise SystemExit("✋ QA_BASE 必须指向 server qa 实例。")
    OUT.mkdir(exist_ok=True)
    async with httpx.AsyncClient(base_url=BASE, trust_env=False, timeout=60.0) as c:
        tok = (await c.post("/auth/login", json={"email": A[0], "password": A[1]})).json()["jwt"]
        H = {"Authorization": f"Bearer {tok}"}
        jobs = (await c.get("/listing/jobs?limit=100", headers=H)).json()
        rows = []
        seen: dict[str, int] = {}
        async with httpx.AsyncClient(trust_env=False, timeout=60.0) as dl:
            for j in jobs:
                if j["status"] not in ("完成", "部分完成") or j["image_count"] < 1:
                    continue
                if j.get("n") != 1:  # 只取 n=1 多样平台×比例样张；A4 多图(n=3/5/7)是并发验证、非共评素材
                    continue
                d = (await c.get(f"/listing/jobs/{j['job_id']}", headers=H)).json()
                plat = d.get("platform") or "?"
                ratio = (d.get("ratio") or "?").replace(":", "x")
                lang = (d.get("modifiers") or {}).get("language", "?")
                for im in d.get("images", []):
                    if im.get("status") != "成功":
                        continue
                    key = f"{plat}-{ratio}-{lang}"
                    seen[key] = seen.get(key, 0) + 1
                    suffix = "" if seen[key] == 1 else f"-{seen[key]}"
                    name = safe(f"{key}{suffix}") + ".png"
                    resp = await dl.get(im["url"])  # fresh signed url, immediate download
                    if resp.status_code == 200:
                        (OUT / name).write_bytes(resp.content)
                        rows.append((name, plat, d.get("ratio"), lang, d.get("size"),
                                     (d.get("prompt") or "")[:36], j["job_id"][:8]))
                        print(f"saved {name} ({len(resp.content)//1024} KB)")
                    else:
                        print(f"FAIL dl {name} HTTP {resp.status_code}")
        lines = [
            "# listing base(gpt-image-2) 花生样张 · 共评素材",
            "",
            f"共 {len(rows)} 张 · 模型 = **gpt-image-2 (base)** · 源图 = 花生精修 · 出图 server qa 实例",
            "",
            "| 文件 | 平台 | 比例 | 语言 | size | prompt(截) | job | QA可用判定 |",
            "|---|---|---|---|---|---|---|---|",
        ]
        for n, p, ra, l, sz, pr, jb in rows:
            lines.append(f"| {n} | {p} | {ra} | {l} | {sz} | {pr} | {jb} | (待填) |")
        (OUT / "index.md").write_text("\n".join(lines) + "\n")
        print(f"\n==== 落盘 {len(rows)} 张 → {OUT} ====")


asyncio.run(main())
