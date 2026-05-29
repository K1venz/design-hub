import hashlib
from pathlib import Path

from design_hub.ports.image_store import ImageStore


class LocalImageStore(ImageStore):
    """把图像字节写到本地目录，返回 file:// url（开发/实测用）。"""

    def __init__(self, base_dir: str) -> None:
        self._dir = Path(base_dir)

    async def save(self, data: bytes, *, suffix: str = ".png") -> str:
        self._dir.mkdir(parents=True, exist_ok=True)
        name = hashlib.sha256(data).hexdigest()[:16] + suffix
        path = self._dir / name
        path.write_bytes(data)
        return path.resolve().as_uri()
