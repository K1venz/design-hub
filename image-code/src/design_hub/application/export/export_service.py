"""导出归档用例（WP-E，PRD §4.4）。

编排：取元数据 → 读源图 → 变换(格式/改尺寸) → 命名规范 → 归档落点(项目/子场景/轮次)
→ 可选 zip 打包。依赖端口（Exporter/ExportStore/ExportQuery，DIP）。
pillow 变换为 CPU 密集，经 asyncio.to_thread 不阻塞事件循环。
"""

from __future__ import annotations

import asyncio
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime

from design_hub.domain.errors import NotFoundError
from design_hub.infrastructure.export import naming
from design_hub.infrastructure.export.packager import zip_bytes
from design_hub.ports.exporter import (
    Exporter,
    ExportFormat,
    ExportItem,
    ExportQuery,
    ExportStore,
)


@dataclass(frozen=True)
class ExportedFile:
    filename: str
    url: str


@dataclass(frozen=True)
class ExportResult:
    package_url: str | None  # zip=True 时为打包 url，否则 None
    files: list[ExportedFile]


@dataclass
class ExportService:
    query: ExportQuery
    exporter: Exporter
    store: ExportStore

    async def _render_one(
        self, item: ExportItem, fmt: ExportFormat, resize: tuple[int, int] | None, now: datetime
    ) -> tuple[str, str, bytes]:
        """单图单格式：读源 → 变换 → 归档写出。返回 (文件名, url, 字节)。"""
        source = await self.store.read(item.source_url)
        data = await asyncio.to_thread(self.exporter.render, source, fmt=fmt, resize=resize)
        filename = naming.export_filename(item, fmt, now)
        rel_path = f"{naming.archive_dir(item)}/{filename}"
        url = await self.store.write(data, rel_path=rel_path)
        return filename, url, data

    async def export(
        self,
        *,
        project_id: int,
        image_ids: Sequence[int],
        formats: Sequence[ExportFormat],
        resize: tuple[int, int] | None = None,
        zip: bool = False,
    ) -> ExportResult:
        if not image_ids:
            raise ValueError("image_ids 不能为空")
        if not formats:
            raise ValueError("formats 不能为空")
        items = await self.query.items(image_ids)
        found = {it.image_id for it in items}
        missing = set(image_ids) - found
        if missing:
            raise NotFoundError(f"图片不存在：{sorted(missing)}")
        outside = [it.image_id for it in items if it.project_id != project_id]
        if outside:
            raise ValueError(f"图片不属于项目 {project_id}：{sorted(outside)}")

        now = datetime.now(UTC)
        files: list[ExportedFile] = []
        blobs: list[tuple[str, bytes]] = []
        # 稳定顺序：按 image_id、格式枚举序
        for item in sorted(items, key=lambda it: it.image_id):
            for fmt in formats:
                filename, url, data = await self._render_one(item, fmt, resize, now)
                files.append(ExportedFile(filename=filename, url=url))
                blobs.append((filename, data))

        package_url: str | None = None
        if zip:
            package = zip_bytes(blobs)
            ts = now.strftime("%Y%m%d_%H%M%S")
            package_url = await self.store.write(
                package, rel_path=f"packages/{naming.project_code(project_id)}_{ts}.zip"
            )
        return ExportResult(package_url=package_url, files=files)

    async def resize_image(
        self, *, image_id: int, width: int, height: int, fmt: ExportFormat = ExportFormat.PNG
    ) -> str:
        item = await self.query.one(image_id)
        if item is None:
            raise NotFoundError(f"图片不存在：{image_id}")
        now = datetime.now(UTC)
        _, url, _ = await self._render_one(item, fmt, (width, height), now)
        return url
