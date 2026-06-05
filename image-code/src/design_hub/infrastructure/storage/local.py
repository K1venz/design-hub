import hashlib
from pathlib import Path

from design_hub.ports.image_store import ImageStore
from design_hub.ports.media_url_signer import MediaUrlSigner


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


class LocalMediaUrlSigner(MediaUrlSigner):
    """本地/dev 签名器：静态拼 {base}/img/{key}（复用 ISSUE-0029 的 nginx /img）。

    本地上传图回显沿用 /img/{key}（与 ISSUE-0030 现状一致，归并为已知项）；
    TOS 实现按桶分别签名，正确区分两桶。
    """

    def __init__(self, base_url: str) -> None:
        self._base = base_url.rstrip("/")

    def generated_url(self, key: str) -> str:
        return f"{self._base}/img/{key}"

    def upload_url(self, key: str) -> str:
        return f"{self._base}/img/{key}"
