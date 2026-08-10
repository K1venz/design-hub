"""二次编辑边界/契约回归（零成本，TE-05/06/16，dev #657 终契约）。

⚠️ 预写：按三方对终契约（#657/#659/#663/#664）。dev /listing/edit 落地 + ops 重建 qa 后跑。
POST /listing/edit extra=forbid，EditRequest = source_image_key + edit_mode(默认delta、非法→400)
+ prompt(min_length=1→422) + modifiers + ratio(delta显式→400/full继承或覆盖)；不收 category。
反解谓词 key∧user_id本人∧status成功 → 随机 sha key=无行→404（与他人/失败张不可区分 anti-enum）。
GHOST 技法：契约非法→400/422（反解前）、合法+随机 key→404（过契约反解无行）。零出图零成本。
用法：QA_BASE=http://localhost:8444 uv run python ../image-qa/edit_boundary_regression.py
"""

import asyncio
import os

import httpx

from qa_auth import login_verified_account

BASE = os.environ.get("QA_BASE", "").rstrip("/")
EP = "/listing/edit"
RKEY = "deadbeefdeadbeef"  # 随机 sha handle（反解无行→404）


def body(key=RKEY, edit_mode="delta", prompt="把背景换成纯白", ratio=None, extra=None):  # noqa: ANN001
    b = {"source_image_key": key, "prompt": prompt,
         "modifiers": {"platform": "淘宝天猫1688", "region": "中国", "language": "中文"}}
    if edit_mode is not None:
        b["edit_mode"] = edit_mode
    if ratio is not None:
        b["ratio"] = ratio
    if extra:
        b.update(extra)
    return b


CASES = [
    ("edit_mode 非法→400", body(edit_mode="超级编辑"), {400}),
    ("prompt 空→422", body(prompt=""), {422}),
    ("prompt 缺→422", {k: v for k, v in body().items() if k != "prompt"}, {422}),
    ("缺 source_image_key→422", {k: v for k, v in body().items() if k != "source_image_key"}, {422}),
    ("delta 显式传 ratio→400", body(edit_mode="delta", ratio="3:4"), {400}),
    ("extra·overlay_texts→422", body(extra={"overlay_texts": ["促销"]}), {422}),
    ("extra·category(不收)→422", body(extra={"category": "FOOD"}), {422}),
    ("extra·未知字段→422", body(extra={"foo": "bar"}), {422}),
    ("合法 delta + 随机 key→过契约 404", body(edit_mode="delta", ratio=None), {404}),
    ("合法 full + 随机 key→过契约 404", body(edit_mode="full"), {404}),
    ("合法 full + ratio 覆盖 + 随机 key→404", body(edit_mode="full", ratio="9:16"), {404}),
    ("默认 edit_mode(省略=delta) + 随机 key→404", body(edit_mode=None), {404}),
]


async def main() -> None:
    if not BASE:
        raise SystemExit("✋ QA_BASE 未设置。")
    print(f"== 二次编辑边界/契约回归（预写）== BASE={BASE} EP={EP}")
    async with httpx.AsyncClient(base_url=BASE, trust_env=False, timeout=60.0) as c:
        session = await login_verified_account(c)
        H = {"Authorization": f"Bearer {session.jwt}"}
        # 端点存在性探测（不走 /openapi.json，docs 默认关后 404）：空 body→路由缺=404
        if (await c.post(EP, headers=H, json={})).status_code == 404:
            raise SystemExit(f"⏳ {EP} 尚未上线（dev 未实现 / ops 未重建 qa）——预写待落地后跑。")
        npass = 0
        for label, b, expect in CASES:
            resp = await c.post(EP, headers=H, json=b)
            ok = resp.status_code in expect
            npass += ok
            extra = "" if ok else f"  <-- got {resp.status_code}: {resp.text[:120]}"
            print(f"  {'PASS' if ok else 'FAIL'}  [{resp.status_code}] {label}{extra}")
        print(f"\n==== 二次编辑边界矩阵：{npass}/{len(CASES)} ====（零出图零成本）")


asyncio.run(main())
