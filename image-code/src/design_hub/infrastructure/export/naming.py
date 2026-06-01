"""文件命名规范 + 归档目录（PRD §4.4，纯函数，便于 QA 校验）。

命名：P{项目号}_客户_场景_轮次N_候选N_档位_YYYYMMDD_HHMMSS.ext
   例 P0012_客户A_S1换背景_轮次2_候选3_精修_20260527_154321.jpg
归档目录：项目编号/子场景/轮次N/
项目号：当前无 project_code 列（D3 待定），暂用 P{project_id:04d} 兜底。
"""

from __future__ import annotations

from datetime import datetime

from design_hub.ports.exporter import ExportFormat, ExportItem

_SCENE_LABEL = {"S1": "S1换背景", "S3": "S3场景图", "S4": "S4多角度"}
_TIER_LABEL = {"draft": "草稿", "standard": "标准", "refine": "精修"}


def _sanitize(token: str) -> str:
    # 去掉路径分隔符/空白，避免破坏目录结构与文件名
    return "".join(c for c in token if c not in '/\\:*?"<>| \t\r\n') or "NA"


def project_code(project_id: int | None) -> str:
    return f"P{project_id:04d}" if project_id is not None else "P0000"


def export_filename(item: ExportItem, fmt: ExportFormat, now: datetime) -> str:
    scene = _SCENE_LABEL.get(item.subscene, item.subscene)
    tier = _TIER_LABEL.get(item.tier, item.tier)
    ts = now.strftime("%Y%m%d_%H%M%S")
    stem = (
        f"{project_code(item.project_id)}_{_sanitize(item.customer)}_{_sanitize(scene)}"
        f"_轮次{item.round_no}_候选{item.candidate_no}_{tier}_{ts}"
    )
    return f"{stem}.{fmt.value}"


def archive_dir(item: ExportItem) -> str:
    """归档相对目录：项目编号/子场景/轮次N。"""
    return f"{project_code(item.project_id)}/{_sanitize(item.subscene)}/轮次{item.round_no}"


def archive_path(item: ExportItem, fmt: ExportFormat, now: datetime) -> str:
    return f"{archive_dir(item)}/{export_filename(item, fmt, now)}"
