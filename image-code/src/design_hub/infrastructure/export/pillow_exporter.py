"""Exporter 的 Pillow 实现（WP-E）：格式转换(JPG/PNG/PDF) + 改尺寸。

纯 CPU 变换、无 I/O。JPG/PDF 无 alpha 通道，转换前统一拍平为 RGB。
"""

import io

from PIL import Image

from design_hub.ports.exporter import Exporter, ExportFormat

_JPEG_QUALITY = 95  # 画质统一默认（PRD §4.4 画质统一；印刷级高画质）


class PillowExporter(Exporter):
    def render(
        self, source: bytes, *, fmt: ExportFormat, resize: tuple[int, int] | None = None
    ) -> bytes:
        with Image.open(io.BytesIO(source)) as opened:
            opened.load()
            img: Image.Image = opened
            if resize is not None:
                w, h = resize
                if w <= 0 or h <= 0:
                    raise ValueError(f"目标尺寸必须为正：{resize}")
                img = img.resize((w, h))
            out = io.BytesIO()
            if fmt is ExportFormat.PNG:
                img.save(out, format="PNG")
            elif fmt is ExportFormat.JPG:
                img.convert("RGB").save(out, format="JPEG", quality=_JPEG_QUALITY)
            elif fmt is ExportFormat.PDF:
                img.convert("RGB").save(out, format="PDF")
            else:  # 防御：StrEnum 已约束，理论不可达
                raise ValueError(f"不支持的导出格式：{fmt}")
        return out.getvalue()
