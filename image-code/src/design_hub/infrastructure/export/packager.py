"""zip 打包（WP-E，纯函数）：把 (文件名, 字节) 列表压成内存 zip 字节。"""

from __future__ import annotations

import io
import zipfile
from collections.abc import Sequence


def zip_bytes(files: Sequence[tuple[str, bytes]]) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for name, data in files:
            zf.writestr(name, data)
    return buf.getvalue()
