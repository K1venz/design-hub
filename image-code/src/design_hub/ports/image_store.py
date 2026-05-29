from abc import ABC, abstractmethod


class ImageStore(ABC):
    """图像落点端口（DIP）：把字节写到某处并返回可访问 url。

    本地实现写磁盘返回 file://；生产实现上传 OSS 返回 https://，按 LSP 替换。
    """

    @abstractmethod
    async def save(self, data: bytes, *, suffix: str = ".png") -> str:
        ...
