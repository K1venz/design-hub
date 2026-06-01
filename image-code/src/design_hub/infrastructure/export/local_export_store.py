"""ExportStore 的本地实现（WP-E）：读 file:// 源图、按相对路径归档写出返回 file://。

OSS 实现按 LSP 替换：read 下载、write 上传返回 https://。
"""

from __future__ import annotations

from pathlib import Path
from urllib.parse import unquote, urlparse

from design_hub.ports.exporter import ExportStore


class LocalExportStore(ExportStore):
    def __init__(self, base_dir: str) -> None:
        self._base = Path(base_dir).resolve()

    async def read(self, url: str) -> bytes:
        parsed = urlparse(url)
        if parsed.scheme != "file":
            raise ValueError(f"LocalExportStore 只支持 file:// 源，收到：{url}")
        return Path(unquote(parsed.path)).read_bytes()

    async def write(self, data: bytes, *, rel_path: str) -> str:
        target = (self._base / rel_path).resolve()
        # 防目录穿越：写出点必须在 base 之内
        if self._base not in target.parents and target != self._base:
            raise ValueError(f"非法导出路径（越界）：{rel_path}")
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)
        return target.as_uri()
