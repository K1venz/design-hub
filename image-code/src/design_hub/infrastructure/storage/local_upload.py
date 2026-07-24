import hashlib
import re
from pathlib import Path

from design_hub.domain.errors import NotFoundError
from design_hub.ports.upload_store import UploadReadError, UploadStore, upload_ns

# content-type ↔ 扩展名白名单（与 UploadService 校验一致）
_EXT_BY_CONTENT_TYPE = {
    "image/png": "png",
    "image/jpeg": "jpg",
    "image/webp": "webp",
}
_CONTENT_TYPE_BY_EXT = {"png": "image/png", "jpg": "image/jpeg", "webp": "image/webp"}
# id = <userNs(12hex)>/<sha(16hex)>.<ext>；严格正则防路径穿越（id 来自客户端）
_ID_RE = re.compile(r"^[0-9a-f]{12}/[0-9a-f]{16}\.(png|jpg|webp)$")


class LocalUploadStore(UploadStore):
    """上传图落本地目录；id=<userNs>/<sha>.<ext>（按用户命名空间隔离，ISSUE-0032）。"""

    def __init__(self, base_dir: str) -> None:
        self._dir = Path(base_dir)

    async def save(self, data: bytes, *, content_type: str, user_id: str) -> str:
        ext = _EXT_BY_CONTENT_TYPE.get(content_type)
        if ext is None:
            raise ValueError(f"不支持的图片类型：{content_type}")
        upload_id = f"{upload_ns(user_id)}/{hashlib.sha256(data).hexdigest()[:16]}.{ext}"
        path = self._dir / upload_id
        path.parent.mkdir(parents=True, exist_ok=True)  # 用户命名空间子目录
        path.write_bytes(data)
        return upload_id

    async def load(self, upload_id: str) -> tuple[bytes, str]:
        if not _ID_RE.match(upload_id):
            raise ValueError(f"非法 upload id：{upload_id}")
        path = self._dir / upload_id
        try:
            if not path.is_file():
                raise NotFoundError(f"上传图不存在：{upload_id}")
            data = path.read_bytes()
        except NotFoundError:
            raise
        except OSError as exc:
            raise UploadReadError(f"读取上传图失败：{upload_id}") from exc
        ext = upload_id.rsplit(".", 1)[1]
        return data, _CONTENT_TYPE_BY_EXT[ext]
