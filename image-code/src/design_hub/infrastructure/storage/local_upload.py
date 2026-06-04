import hashlib
import re
from pathlib import Path

from design_hub.domain.errors import NotFoundError
from design_hub.ports.upload_store import UploadStore

# content-type ↔ 扩展名白名单（与 UploadService 校验一致）
_EXT_BY_CONTENT_TYPE = {
    "image/png": "png",
    "image/jpeg": "jpg",
    "image/webp": "webp",
}
_CONTENT_TYPE_BY_EXT = {"png": "image/png", "jpg": "image/jpeg", "webp": "image/webp"}
# id = sha256(data)[:16].<ext>；约束防路径穿越（GET /uploads/{id} 的 id 来自客户端）
_ID_RE = re.compile(r"^[0-9a-f]{16}\.(png|jpg|webp)$")


class LocalUploadStore(UploadStore):
    """上传图落本地目录；id=sha256(data)[:16].<ext>，按 id 读回 bytes + 推断 content-type。"""

    def __init__(self, base_dir: str) -> None:
        self._dir = Path(base_dir)

    async def save(self, data: bytes, *, content_type: str) -> str:
        ext = _EXT_BY_CONTENT_TYPE.get(content_type)
        if ext is None:
            raise ValueError(f"不支持的图片类型：{content_type}")
        self._dir.mkdir(parents=True, exist_ok=True)
        upload_id = f"{hashlib.sha256(data).hexdigest()[:16]}.{ext}"
        (self._dir / upload_id).write_bytes(data)
        return upload_id

    async def load(self, upload_id: str) -> tuple[bytes, str]:
        if not _ID_RE.match(upload_id):
            raise ValueError(f"非法 upload id：{upload_id}")
        path = self._dir / upload_id
        if not path.is_file():
            raise NotFoundError(f"上传图不存在：{upload_id}")
        ext = upload_id.rsplit(".", 1)[1]
        return path.read_bytes(), _CONTENT_TYPE_BY_EXT[ext]
