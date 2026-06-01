"""导出归档端口（WP-E，DIP）。

三个 export 边界端口集中于此：
- Exporter：纯图像变换（格式转换 + 改尺寸），pillow 是一种实现。
- ExportStore：导出落点（读源图字节 + 按结构化相对路径写出并返回 url），复用 ImageStore 思路。
- ExportQuery：读侧，按 image_ids 取出命名/归档所需的 job/project 元数据。
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Sequence
from dataclasses import dataclass
from enum import StrEnum


class ExportFormat(StrEnum):
    JPG = "jpg"
    PNG = "png"
    PDF = "pdf"


class Exporter(ABC):
    """纯图像变换端口：源字节 →（可选改尺寸）→ 目标格式字节。CPU 密集、无 I/O。"""

    @abstractmethod
    def render(
        self, source: bytes, *, fmt: ExportFormat, resize: tuple[int, int] | None = None
    ) -> bytes:
        ...


class ExportStore(ABC):
    """导出落点端口：读源图（file:// 等）、按相对路径归档写出并返回可访问 url。

    本地实现读写磁盘 file://；生产实现走 OSS，按 LSP 替换。
    """

    @abstractmethod
    async def read(self, url: str) -> bytes:
        ...

    @abstractmethod
    async def write(self, data: bytes, *, rel_path: str) -> str:
        ...


@dataclass(frozen=True)
class ExportItem:
    """导出一张图所需的元数据（命名规范 + 归档目录的数据来源）。"""

    image_id: int
    source_url: str
    project_id: int | None
    customer: str
    subscene: str
    tier: str
    round_no: int
    candidate_no: int  # 同一 job 内按 id 升序的候选序号（1-based）


class ExportQuery(ABC):
    """导出读侧端口：generated_image ⋈ generation_job 取命名/归档元数据。"""

    @abstractmethod
    async def items(self, image_ids: Sequence[int]) -> list[ExportItem]:
        """返回 image_ids 中存在的图项（顺序不保证；缺失的由用例校验）。"""
        ...

    @abstractmethod
    async def one(self, image_id: int) -> ExportItem | None:
        ...
