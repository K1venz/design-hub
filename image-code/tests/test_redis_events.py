import asyncio
import json
from typing import Any

from design_hub.domain.enums import TaskEventType
from design_hub.domain.models import TaskEvent
from design_hub.infrastructure.queue.redis_streams import RedisJobEventStream
from design_hub.ports.events import ReplayableEvent


class _FakeRedis:
    def __init__(self) -> None:
        self.calls: list[tuple[str, tuple[object, ...], dict[str, object]]] = []
        self.read_result: object = []

    async def xadd(self, *args: object, **kwargs: object) -> str:
        self.calls.append(("xadd", args, kwargs))
        return "15-0"

    async def expire(self, *args: object, **kwargs: object) -> bool:
        self.calls.append(("expire", args, kwargs))
        return True

    async def xread(self, *args: object, **kwargs: object) -> Any:
        self.calls.append(("xread", args, kwargs))
        return self.read_result


def test_job_event_is_bounded_expires_and_replays_after_event_id() -> None:
    async def run() -> None:
        redis = _FakeRedis()
        events = RedisJobEventStream(redis)
        event = TaskEvent(
            job_id="job-1",
            type=TaskEventType.IMAGE_GENERATED,
            data={"image_key": "result.png", "seed": 0},
        )

        assert await events.publish(event) == "15-0"
        redis.read_result = [
            (
                "design-hub:events:job-1",
                [
                    (
                        "15-0",
                        {
                            "event_type": "image_generated",
                            "data": json.dumps(event.data, ensure_ascii=False),
                        },
                    )
                ],
            )
        ]
        replay = await events.read(job_id="job-1", after_id="14-0", block_ms=1000)

        assert replay == (ReplayableEvent(redis_id="15-0", event=event),)
        assert redis.calls == [
            (
                "xadd",
                (
                    "design-hub:events:job-1",
                    {
                        "event_type": "image_generated",
                        "data": '{"image_key": "result.png", "seed": 0}',
                    },
                ),
                {"maxlen": 100, "approximate": True},
            ),
            ("expire", ("design-hub:events:job-1", 86400), {}),
            (
                "xread",
                ({"design-hub:events:job-1": "14-0"},),
                {"count": 100, "block": 1000},
            ),
        ]

    asyncio.run(run())
