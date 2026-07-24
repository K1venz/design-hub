import hashlib
from abc import ABC, abstractmethod


def upload_ns(user_id: str) -> str:
    """用户命名空间 = sha256(user_id)[:12]。上传图 key 以此为前缀，实现按用户隔离（无需建表）。"""
    return hashlib.sha256(user_id.encode("utf-8")).hexdigest()[:12]


def owns(upload_id: str, user_id: str) -> bool:
    """upload_id 是否属于该用户（key 前缀 == 其命名空间）。"""
    return upload_id.startswith(f"{upload_ns(user_id)}/")


class UploadReadError(OSError):
    """上传图存储可用，但本次读取因 I/O 或网络故障失败。"""


class UploadStore(ABC):
    """上传图落点端口（DIP）：存字节返回 id（含用户命名空间），按 id 读回 (bytes, content_type)。

    服务「先上传预览 → 再出图」两步流（ISSUE-0026）；id = `<userNs>/<sha>.<ext>`，
    归属隔离（ISSUE-0032）由前缀承载，取图前经 owns() 校验。
    本地实现写磁盘，TOS 实现按 LSP 替换。
    """

    @abstractmethod
    async def save(self, data: bytes, *, content_type: str, user_id: str) -> str:
        """存字节，返回 upload id（`<userNs>/<sha>.<ext>`）。"""
        ...

    @abstractmethod
    async def load(self, upload_id: str) -> tuple[bytes, str]:
        """读回图片；非法 → ValueError，不存在 → NotFoundError，I/O 失败 → UploadReadError。"""
        ...
