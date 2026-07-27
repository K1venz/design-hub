from abc import ABC, abstractmethod
from dataclasses import dataclass


@dataclass(frozen=True)
class StoredImage:
    key: str
    url: str


class ImageStore(ABC):
    """出图落点端口（DIP）：写入出图字节返回稳定 key + 即时 url；按 key 读回字节。

    本地实现写 generated/ 目录返回 /img url；生产实现走 TOS generate 桶返回
    预签名 https://，按 LSP 替换。load 供二次编辑读源图（ISSUE-0040）。
    """

    @abstractmethod
    async def save(self, data: bytes, *, suffix: str = ".png") -> StoredImage:
        ...

    @abstractmethod
    async def load(self, image_key: str) -> bytes:
        """按 image_key 读回出图字节；不存在 → NotFoundError（404 anti-enum 口径）。"""
        ...
