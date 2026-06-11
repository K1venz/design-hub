"""A-2 nginx 加固 安全 smoke（闸②，部署后跑）。

⚠️ 必须打**公网 nginx 入口** `https://14.103.51.191`（curl -k 自签）——不走 8445 隧道
（隧道直连 api:8000 绕过 nginx，会误判 docs 仍开/无安全头）。零成本（无 auth 无出图）。
核 ① docs/openapi/redoc/metrics **根 + /api/ 两族**全公网 404/403（coordinator #608 catch：
   /api/* 经 rewrite 去前缀直通后端 FastAPI 默认开 docs，必须单独堵）② 安全头在。
429 频控 prod 验证走 rate_limit_regression.py（QA_BASE=http://localhost:8445）。
用法：PUBLIC_BASE=https://14.103.51.191 uv run python ../image-qa/security_smoke.py
"""

import os

import httpx

BASE = os.environ.get("PUBLIC_BASE", "https://14.103.51.191").rstrip("/")
# 根族 + /api/ 族（#608：两族都要堵）
BLOCK_PATHS = [
    "/docs", "/redoc", "/openapi.json", "/metrics",
    "/api/docs", "/api/redoc", "/api/openapi.json", "/api/metrics",
]
SEC_HEADERS = {
    "strict-transport-security": None,         # 存在即可
    "x-frame-options": "DENY",
    "x-content-type-options": "nosniff",
    "referrer-policy": None,
}


def main() -> None:
    print(f"== A-2 安全 smoke（公网 nginx 入口）== BASE={BASE}")
    npass = ntotal = 0
    with httpx.Client(base_url=BASE, verify=False, trust_env=False, timeout=15.0, follow_redirects=False) as c:
        print("\n[① docs/metrics 公网屏蔽：根 + /api/ 两族 → 404/403]")
        for p in BLOCK_PATHS:
            ntotal += 1
            try:
                code = c.get(p).status_code
            except httpx.HTTPError as e:
                code = f"ERR {type(e).__name__}"
            ok = code in (404, 403)
            npass += ok
            print(f"  {'PASS' if ok else 'FAIL'}  {p} → {code}")

        print("\n[② 安全响应头在]")
        r = c.get("/")
        for h, want in SEC_HEADERS.items():
            ntotal += 1
            val = r.headers.get(h)
            ok = val is not None and (want is None or want.lower() in val.lower())
            npass += ok
            print(f"  {'PASS' if ok else 'FAIL'}  {h}: {val!r}" + (f"（期望含 {want}）" if want and not ok else ""))
        ntotal += 1
        st_off = "server" not in r.headers or "nginx/" not in r.headers.get("server", "").lower()
        npass += st_off
        print(f"  {'PASS' if st_off else 'FAIL'}  server_tokens off（Server 头={r.headers.get('server')!r}）")

    print(f"\n==== A-2 安全 smoke：{npass}/{ntotal} ====（429 频控走 rate_limit_regression 打 8445）")


main()
