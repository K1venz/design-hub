"""世界 A 移除·DB schema 校验（ISSUE-0046 验收③，dev DROP 迁移落 qa 后跑）。

断言：children-first DROP 的 **8 表已不存在** + **6 张保留表完好**（cost_ledger/listing
计费命脉在）。qa env 验 schema（无 zhaokai）；prod 数据完整(zhaokai 不动)归 ops smoke。

安全边界：QA 不经手 DB 凭证。脚本从 env 读 QA_DB_URL（run 时环境注入即自助核）；
未设/连不上 → 打印期望 manifest，交 @ops 跑 `SHOW TABLES` 我核 output（老规矩）。
不硬编码任何 secret。
用法：QA_DB_URL=mysql+pymysql://dh_qa_ro:***@127.0.0.1:13306/design_hub_qa \
      uv run python ../image-qa/world_a_db_check.py
"""

import os
import sys

DROPPED = [  # children-first，应全部消失
    "generated_image", "generation_job", "deliverable", "revision",
    "asset", "brief", "project", "customer",
]
KEPT = [  # 计费命脉 + 基建，必须完好
    "model_config", "cost_ledger", "app_user",
    "listing_job", "listing_image", "listing_job_input",
]


def manifest() -> None:
    print("== 世界 A 移除 DB 校验 manifest（交 @ops 跑 `SHOW TABLES;` 核对）==")
    print(f"  应【不存在】(8 表 DROP，children-first)：{DROPPED}")
    print(f"  应【完好存在】(6 保留表)：{KEPT}")
    print("  额外：cost_ledger / listing_* 行数应与迁移前一致（prod 上 zhaokai 全量不动）。")


def main() -> None:
    url = os.environ.get("QA_DB_URL", "").strip()
    if not url:
        print("ℹ️ QA_DB_URL 未设置——QA 无 DB 凭证，转 manifest 交 ops 核。\n")
        manifest()
        return
    try:
        from sqlalchemy import create_engine, text
    except ImportError:
        print("ℹ️ 无 sqlalchemy，转 manifest 交 ops 核。\n")
        manifest()
        return
    try:
        eng = create_engine(url)
        with eng.connect() as conn:
            rows = conn.execute(
                text("SELECT table_name FROM information_schema.tables WHERE table_schema = DATABASE()")
            ).fetchall()
    except Exception as e:  # noqa: BLE001 — I/O：连不上就降级 manifest，不掩盖
        print(f"ℹ️ 连库失败（{type(e).__name__}: {e}）——转 manifest 交 ops 核。\n")
        manifest()
        return

    tables = {r[0] for r in rows}
    npass = ntotal = 0

    def ck(label, ok, extra=""):  # noqa: ANN001
        nonlocal npass, ntotal
        ntotal += 1
        npass += bool(ok)
        print(f"  {'PASS' if ok else '🔴 FAIL'}  {label}{('  ' + extra) if extra else ''}")

    print(f"== 世界 A 移除 DB 校验 == 库内 {len(tables)} 表")
    print("\n[8 表已 DROP]")
    for t in DROPPED:
        ck(f"{t} 不存在", t not in tables, "" if t not in tables else "<<< 仍在！DROP 未生效")
    print("\n[6 保留表完好]")
    for t in KEPT:
        ck(f"{t} 存在", t in tables, "" if t in tables else "<<< 丢了！误删保留表")

    print(f"\n==== DB 校验：{npass}/{ntotal} ====")
    if npass != ntotal:
        sys.exit("🔴 schema 不符预期，STOP 报 coordinator。")


main()
