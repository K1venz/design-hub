from abc import ABC, abstractmethod


class AssetStore(ABC):
    """素材落点端口（DIP）：上传字节写到某处并返回可访问 url，且可按 url 读回字节。

    与只写的 ImageStore（出图落点）区分：素材是出图输入，图生图(/images/edits)需把
    选中素材字节回灌给 Provider，故本端口需 load。本地实现读写磁盘，OSS 实现走对象存储。
    """

    @abstractmethod
    async def save(self, data: bytes, *, suffix: str = ".png") -> str:
        ...

    @abstractmethod
    async def load(self, url: str) -> bytes:
        ...
