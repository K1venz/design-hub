# /// script
# requires-python = ">=3.12"
# dependencies = ["httpx>=0.28"]
# ///
"""gpt-image-2 中转站实测探针。

回答 ISSUE-0002 / spec §6 的开放问题：
  1) 返回格式：data[] 是 url 还是 b64_json（决定 openai_compat.py 的解析）
  2) 质量 & 计费：是否接受 quality 参数；按 usage 折算真实单价
  3) 错误映射：--probe-bad 看 4xx 返回什么状态码（验证决策①）

用法（每个中转站各跑一次）：
  RELAY_BASE_URL=https://诗云的/v1 RELAY_API_KEY=sk-xxx \
    uv run scripts/probe_gpt_image_relay.py

  # 或用参数：
  uv run scripts/probe_gpt_image_relay.py \
    --base-url https://api易的/v1 --api-key sk-xxx --quality medium

  # 顺带探一次坏请求，观察 4xx：
  uv run scripts/probe_gpt_image_relay.py --probe-bad

注意：会真实计费一次（一张图），单张几分到一两毛。脚本不写产品代码、不碰 image-code。
"""

from __future__ import annotations

import argparse
import asyncio
import base64
import os
import time
from pathlib import Path
from typing import Any

import httpx

# 官方 gpt-image-2 token 价（USD / 1M tokens），用于按 usage 折算单价
PRICE_TEXT_IN = 5.0
PRICE_IMAGE_IN = 8.0
PRICE_IMAGE_OUT = 30.0


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="gpt-image-2 中转站实测探针")
    p.add_argument("--base-url", default=os.getenv("RELAY_BASE_URL"),
                   help="中转站 OpenAI 兼容根地址，含 /v1，如 https://x.com/v1")
    p.add_argument("--api-key", default=os.getenv("RELAY_API_KEY"))
    p.add_argument("--model", default=os.getenv("RELAY_MODEL", "gpt-image-2"))
    p.add_argument("--prompt", default="一只戴墨镜的柴犬，扁平插画风，纯色背景")
    p.add_argument("--size", default="1024x1024")
    p.add_argument("--quality", default="medium",
                   help='low|medium|high；传 "omit" 则不带 quality，观察默认档')
    p.add_argument("--response-format", default="omit",
                   help='url|b64_json|omit；默认 omit 以观察中转站默认返回格式')
    p.add_argument("--timeout", type=float, default=120.0)
    p.add_argument("--probe-bad", action="store_true",
                   help="额外发一个非法请求(size=1x1)看 4xx 状态码")
    return p.parse_args()


def mask(key: str) -> str:
    return f"{key[:6]}…{key[-4:]}" if len(key) > 12 else "***"


def build_payload(args: argparse.Namespace, *, bad: bool = False) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "model": args.model,
        "prompt": args.prompt,
        "n": 1,
        "size": "1x1" if bad else args.size,  # 1x1 触发参数校验错误
    }
    if args.quality != "omit":
        payload["quality"] = args.quality
    if args.response_format != "omit":
        payload["response_format"] = args.response_format
    return payload


def estimate_cost_usd(usage: dict[str, Any]) -> float | None:
    """按官方价折算单张 USD；usage 结构缺失则返回 None。"""
    if not isinstance(usage, dict):
        return None
    out = usage.get("output_tokens", 0)
    details = usage.get("input_tokens_details", {}) or {}
    text_in = details.get("text_tokens", usage.get("input_tokens", 0))
    image_in = details.get("image_tokens", 0)
    return (
        text_in * PRICE_TEXT_IN / 1e6
        + image_in * PRICE_IMAGE_IN / 1e6
        + out * PRICE_IMAGE_OUT / 1e6
    )


def inspect_response(body: dict[str, Any], latency_ms: int) -> None:
    print(f"  顶层字段: {sorted(body.keys())}")
    data = body.get("data") or []
    if not data:
        print("  [!] data 为空，无法判断返回格式")
    else:
        item = data[0]
        has_url = bool(item.get("url"))
        b64 = item.get("b64_json")
        if has_url:
            print(f"  [返回格式] ✅ url  → {item['url'][:80]}")
        elif b64:
            print(f"  [返回格式] ⚠️ b64_json（长度 {len(b64)}），需在 adapter 解码")
            out_path = Path(__file__).parent / "probe_out.png"
            out_path.write_bytes(base64.b64decode(b64))
            print(f"            已存盘 {out_path}，可肉眼看质量档")
        else:
            print(f"  [返回格式] [!] 既无 url 也无 b64_json，item 键: {sorted(item.keys())}")

    usage = body.get("usage")
    if usage:
        print(f"  [usage] {usage}")
        cost = estimate_cost_usd(usage)
        if cost is not None:
            print(f"  [折算单价] ≈ ${cost:.4f}/张 ≈ ¥{cost * 7.2:.3f}/张（按官方价估）")
    else:
        print("  [usage] 无 usage 块 → 该中转站不回传用量，单价需自行按标价核算")
    print(f"  [延迟] {latency_ms} ms")


async def fire(client: httpx.AsyncClient, url: str, payload: dict[str, Any],
               headers: dict[str, str], timeout: float) -> None:
    start = time.perf_counter()
    try:
        resp = await client.post(url, json=payload, headers=headers, timeout=timeout)
    except httpx.TimeoutException as exc:
        print(f"  [!] 超时（IO 域 → 真实 adapter 会触发 failover）: {exc}")
        return
    except httpx.RequestError as exc:
        print(f"  [!] 连接错误（IO 域 → failover）: {exc}")
        return
    latency_ms = int((time.perf_counter() - start) * 1000)
    print(f"  HTTP {resp.status_code}")
    if resp.status_code >= 400:
        # 决策①的关键证据：看 4xx vs 5xx，决定该上抛还是切备
        bucket = "应上抛(DomainError)" if resp.status_code in (400, 422) else "应切备(ProviderTimeout)"
        print(f"  [错误映射] {resp.status_code} → 按 spec: {bucket}")
        print(f"  返回体: {resp.text[:400]}")
        return
    inspect_response(resp.json(), latency_ms)


async def main() -> None:
    args = parse_args()
    if not args.base_url or not args.api_key:
        raise SystemExit(
            "缺少 --base-url / --api-key（或 RELAY_BASE_URL / RELAY_API_KEY 环境变量）"
        )
    url = f"{args.base_url.rstrip('/')}/images/generations"
    headers = {"Authorization": f"Bearer {args.api_key}"}

    print("=" * 60)
    print(f"中转站: {url}")
    print(f"key: {mask(args.api_key)} | model: {args.model} | "
          f"quality: {args.quality} | size: {args.size} | response_format: {args.response_format}")
    print("=" * 60)

    async with httpx.AsyncClient() as client:
        print("\n[1] 正常出图探测")
        await fire(client, url, build_payload(args), headers, args.timeout)

        if args.probe_bad:
            print("\n[2] 坏请求探测（size=1x1，验证决策①的 4xx 行为）")
            await fire(client, url, build_payload(args, bad=True), headers, args.timeout)


if __name__ == "__main__":
    asyncio.run(main())
