import hashlib
from pathlib import Path
from urllib.parse import unquote, urlparse

from design_hub.ports.asset_store import AssetStore


class LocalAssetStore(AssetStore):
    """把素材字节写到本地目录、按 file:// url 读回（开发/实测用）。

    OSS 实现按 LSP 替换：save 上传返回 https://，load 下载回字节。
    """

    def __init__(self, base_dir: str) -> None:
        self._dir = Path(base_dir)

    async def save(self, data: bytes, *, suffix: str = ".png") -> str:
        self._dir.mkdir(parents=True, exist_ok=True)
        name = hashlib.sha256(data).hexdigest()[:16] + suffix
        path = self._dir / name
        path.write_bytes(data)
        return path.resolve().as_uri()

    async def load(self, url: str) -> bytes:
        parsed = urlparse(url)
        if parsed.scheme != "file":
            raise ValueError(f"LocalAssetStore 只支持 file:// url，收到：{url}")
        return Path(unquote(parsed.path)).read_bytes()
