"""ExportStore 的本地实现（WP-E）：按文件名从出图目录读源图、归档写出返回 file://。

源 url 自 ISSUE-0029 起为 web 路径（/img/<name> 或 https://host/img/<name>），不再 file://；
read 统一取 url 文件名从 source_dir（出图目录）读字节，兼容历史 file://。
OSS 实现按 LSP 替换：read 下载、write 上传返回 https://。
"""

from __future__ import annotations

from pathlib import Path
from urllib.parse import urlparse

from design_hub.ports.exporter import ExportStore


class LocalExportStore(ExportStore):
    def __init__(self, base_dir: str, *, source_dir: str) -> None:
        self._base = Path(base_dir).resolve()
        self._source = Path(source_dir).resolve()

    async def read(self, url: str) -> bytes:
        # 出图 url 为 web 路径(/img/<name>) 或历史 file://；统一按文件名从出图目录读
        name = Path(urlparse(url).path).name
        if not name:
            raise ValueError(f"无法从 url 解析文件名：{url}")
        return (self._source / name).read_bytes()

    async def write(self, data: bytes, *, rel_path: str) -> str:
        target = (self._base / rel_path).resolve()
        # 防目录穿越：写出点必须在 base 之内
        if self._base not in target.parents and target != self._base:
            raise ValueError(f"非法导出路径（越界）：{rel_path}")
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)
        return target.as_uri()
