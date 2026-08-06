import asyncio
import json
from collections.abc import AsyncIterator

import pytest

from design_hub.application.chat.orchestrator import ChatEvent
from design_hub.interface.api.routes.chat import _stream_chat_events
from design_hub.ports.media_url_signer import MediaUrlSigner


class StubSigner(MediaUrlSigner):
    def generated_url(self, key: str) -> str:
        return f"https://img.test/{key}?signed=1"

    def upload_url(self, key: str) -> str:
        return f"https://upload.test/{key}?signed=1"


def test_chat_stream_emits_comment_heartbeat_without_cancelling_source() -> None:
    async def _impl() -> None:
        release = asyncio.Event()

        async def source() -> AsyncIterator[ChatEvent]:
            await release.wait()
            yield ChatEvent("assistant_end", {"status": "complete"})

        stream = _stream_chat_events(
            source(),
            StubSigner(),
            heartbeat_seconds=0.01,
        )
        assert await anext(stream) == ": keep-alive\n\n"

        release.set()
        payload = await anext(stream)
        assert payload.startswith("event: assistant_end\n")
        with pytest.raises(StopAsyncIteration):
            await anext(stream)

    asyncio.run(_impl())


def test_chat_stream_presents_nested_image_job_event() -> None:
    async def _impl() -> None:
        async def source() -> AsyncIterator[ChatEvent]:
            yield ChatEvent(
                "job_event",
                {
                    "job_id": "job-1",
                    "redis_id": "10-0",
                    "type": "image_generated",
                    "data": {
                        "item_id": "item-1",
                        "image_key": "result.png",
                    },
                },
            )

        stream = _stream_chat_events(source(), StubSigner())
        payload = await anext(stream)
        data = json.loads(payload.split("data: ", maxsplit=1)[1])

        assert data["redis_id"] == "10-0"
        assert data["data"]["image_key"] == "result.png"
        assert data["data"]["url"] == "https://img.test/result.png?signed=1"

    asyncio.run(_impl())
