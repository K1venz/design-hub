import hashlib
from pathlib import Path

from design_hub.ports.image_store import ImageStore


class LocalImageStore(ImageStore):
    """把图像字节写到本地目录，返回 web 可访问 url（ISSUE-0029）。

    url = f"{public_base_url}/img/{name}"：
    - public_base_url 非空 → 绝对地址 https://host/img/<sha16>.png（prod / dev 跨源）；
    - 为空 → 相对 /img/<sha16>.png（同源，靠 nginx/dev 服务 /img/ 静态目录）。
    不再返回 file://（浏览器禁止网页加载本地资源）。OSS 实现按 LSP 替换返回 https://。
    """

    def __init__(self, base_dir: str, *, public_base_url: str = "") -> None:
        self._dir = Path(base_dir)
        self._public_base_url = public_base_url.rstrip("/")

    async def save(self, data: bytes, *, suffix: str = ".png") -> str:
        self._dir.mkdir(parents=True, exist_ok=True)
        name = hashlib.sha256(data).hexdigest()[:16] + suffix
        (self._dir / name).write_bytes(data)
        return f"{self._public_base_url}/img/{name}"
