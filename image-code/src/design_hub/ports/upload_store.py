from abc import ABC, abstractmethod


class UploadStore(ABC):
    """上传图临时落点端口（DIP）：存字节返回路径安全的 id，按 id 读回 (bytes, content_type)。

    与项目素材的 AssetStore 区分：本端口服务「先上传预览 → 再出图」两步流（ISSUE-0026），
    原生以 (id, content_type) 语义工作，供 GET /uploads/{id} 代理预览。
    本地实现写磁盘，OSS 实现按 LSP 替换。
    """

    @abstractmethod
    async def save(self, data: bytes, *, content_type: str) -> str:
        """存字节，返回 upload id（路径安全的存储键）。"""
        ...

    @abstractmethod
    async def load(self, upload_id: str) -> tuple[bytes, str]:
        """按 id 读回 (bytes, content_type)；id 非法 → ValueError，不存在 → NotFoundError。"""
        ...
