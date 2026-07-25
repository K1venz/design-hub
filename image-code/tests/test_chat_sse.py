import asyncio
from collections.abc import AsyncIterator

import pytest

from design_hub.application.chat.orchestrator import ChatEvent
from design_hub.interface.api.routes.chat import _stream_chat_events


def test_chat_stream_emits_comment_heartbeat_without_cancelling_source() -> None:
    async def _impl() -> None:
        release = asyncio.Event()

        async def source() -> AsyncIterator[ChatEvent]:
            await release.wait()
            yield ChatEvent("assistant_end", {"status": "complete"})

        stream = _stream_chat_events(source(), heartbeat_seconds=0.01)
        assert await anext(stream) == ": keep-alive\n\n"

        release.set()
        payload = await anext(stream)
        assert payload.startswith("event: assistant_end\n")
        with pytest.raises(StopAsyncIteration):
            await anext(stream)

    asyncio.run(_impl())
