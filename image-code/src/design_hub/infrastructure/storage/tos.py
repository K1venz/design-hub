"""火山引擎 TOS 对象存储适配器（私有桶 + 预签名 url）。

tos SDK 为同步：网络调用(put/get)包 asyncio.to_thread 不阻塞事件循环；
预签名为本地计算(无网络)，可同步。出图结果与上传图分属两桶。
"""

import asyncio
import hashlib
from pathlib import Path
from typing import Any

import tos

from design_hub.config.settings import Settings
from design_hub.domain.errors import NotFoundError
from design_hub.ports.exporter import ExportStore
from design_hub.ports.image_store import ImageStore
from design_hub.ports.media_url_signer import MediaUrlSigner
from design_hub.ports.upload_store import UploadStore, upload_ns

_EXT_BY_CONTENT_TYPE = {"image/png": "png", "image/jpeg": "jpg", "image/webp": "webp"}
_CONTENT_TYPE_BY_EXT = {"png": "image/png", "jpg": "image/jpeg", "webp": "image/webp"}


def build_tos_client(settings: Settings) -> Any:
    return tos.TosClientV2(
        settings.tos_access_key.get_secret_value(),
        settings.tos_secret_key.get_secret_value(),
        settings.tos_endpoint,
        settings.tos_region,
    )


def _signed_get(client: Any, bucket: str, key: str, ttl: int) -> str:
    out = client.pre_signed_url(tos.HttpMethodType.Http_Method_Get, bucket, key, expires=ttl)
    return str(out.signed_url)


class TosMediaUrlSigner(MediaUrlSigner):
    def __init__(self, client: Any, generate_bucket: str, upload_bucket: str, ttl: int) -> None:
        self._client = client
        self._gen = generate_bucket
        self._up = upload_bucket
        self._ttl = ttl

    def generated_url(self, key: str) -> str:
        return _signed_get(self._client, self._gen, key, self._ttl)

    def upload_url(self, key: str) -> str:
        return _signed_get(self._client, self._up, key, self._ttl)


class TosImageStore(ImageStore):
    """出图结果落 generate 桶；save 返回签名 url（供 SSE 即时显示）。"""

    def __init__(self, client: Any, bucket: str, signer: MediaUrlSigner) -> None:
        self._client = client
        self._bucket = bucket
        self._signer = signer

    async def save(self, data: bytes, *, suffix: str = ".png") -> str:
        key = hashlib.sha256(data).hexdigest()[:16] + suffix
        await asyncio.to_thread(self._client.put_object, self._bucket, key, content=data)
        return self._signer.generated_url(key)


class TosUploadStore(UploadStore):
    """上传图落 upload 桶；id=key=<sha16>.<ext>；load 从 TOS 下载字节（喂 edits / 预览代理）。"""

    def __init__(self, client: Any, bucket: str) -> None:
        self._client = client
        self._bucket = bucket

    async def save(self, data: bytes, *, content_type: str, user_id: str) -> str:
        ext = _EXT_BY_CONTENT_TYPE.get(content_type)
        if ext is None:
            raise ValueError(f"不支持的图片类型：{content_type}")
        key = f"{upload_ns(user_id)}/{hashlib.sha256(data).hexdigest()[:16]}.{ext}"
        await asyncio.to_thread(self._client.put_object, self._bucket, key, content=data)
        return key

    async def load(self, upload_id: str) -> tuple[bytes, str]:
        ext = upload_id.rsplit(".", 1)[-1] if "." in upload_id else ""
        content_type = _CONTENT_TYPE_BY_EXT.get(ext)
        if content_type is None:
            raise ValueError(f"非法 upload id：{upload_id}")
        try:
            obj = await asyncio.to_thread(self._client.get_object, self._bucket, upload_id)
            data = await asyncio.to_thread(obj.read)
        except tos.exceptions.TosServerError as exc:
            if getattr(exc, "status_code", None) == 404:
                raise NotFoundError(f"上传图不存在：{upload_id}") from exc
            raise
        return data, content_type


class TosExportStore(ExportStore):
    """导出（ISSUE-0034）：源图从 generate 桶按 key 读回；产物仍落本地（无导出桶）。"""

    def __init__(self, client: Any, source_bucket: str, base_dir: str) -> None:
        self._client = client
        self._bucket = source_bucket
        self._base = Path(base_dir).resolve()

    async def read(self, url: str) -> bytes:
        key = url.split("?")[0].rsplit("/", 1)[-1]  # 源图 image_key
        obj = await asyncio.to_thread(self._client.get_object, self._bucket, key)
        data: bytes = await asyncio.to_thread(obj.read)
        return data

    async def write(self, data: bytes, *, rel_path: str) -> str:
        target = (self._base / rel_path).resolve()
        # 防目录穿越：写出点必须在 base 之内
        if self._base not in target.parents and target != self._base:
            raise ValueError(f"非法导出路径（越界）：{rel_path}")
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)
        return target.as_uri()
