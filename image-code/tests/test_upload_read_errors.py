import asyncio

import pytest
import tos

from design_hub.infrastructure.storage.tos import TosUploadStore
from design_hub.ports.upload_store import UploadReadError


class _FailingTosClient:
    def get_object(self, bucket: str, key: str) -> None:
        raise tos.exceptions.TosClientError("network unavailable")


def test_tos_client_error_becomes_upload_read_error() -> None:
    async def _impl() -> None:
        store = TosUploadStore(_FailingTosClient(), "uploads")

        with pytest.raises(UploadReadError):
            await store.load("000000000000/image.png")

    asyncio.run(_impl())
