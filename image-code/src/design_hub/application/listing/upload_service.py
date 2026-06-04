from dataclasses import dataclass

from design_hub.ports.upload_store import UploadStore

_MAX_BYTES = 10 * 1024 * 1024
_ALLOWED_CONTENT_TYPES = {"image/png", "image/jpeg", "image/webp"}


@dataclass
class UploadService:
    """上传图用例（SRP）：fail-fast 校验大小/格式 → 落 UploadStore；按 id 读回供预览。"""

    store: UploadStore

    async def save(self, *, data: bytes, content_type: str) -> str:
        if not data:
            raise ValueError("上传文件为空")
        if len(data) > _MAX_BYTES:
            raise ValueError(f"图片超过 10MB（{len(data)} 字节）")
        if content_type not in _ALLOWED_CONTENT_TYPES:
            raise ValueError(f"不支持的图片格式：{content_type or '未知'}（仅 png/jpg/webp）")
        return await self.store.save(data, content_type=content_type)

    async def load(self, upload_id: str) -> tuple[bytes, str]:
        return await self.store.load(upload_id)
