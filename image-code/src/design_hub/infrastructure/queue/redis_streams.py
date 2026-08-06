import json
from collections.abc import Mapping, Sequence
from typing import Any, Protocol

from redis.exceptions import ResponseError

from design_hub.domain.enums import TaskEventType
from design_hub.domain.models import TaskEvent
from design_hub.domain.tasking import TaskMessage
from design_hub.ports.events import ReplayableEvent
from design_hub.ports.task_broker import Delivery

_GENERATION_STREAM = "design-hub:generation:v1"
_GENERATION_GROUP = "generation-workers-v1"
_EVENT_PREFIX = "design-hub:events:"
_EVENT_MAX_LENGTH = 100
_EVENT_TTL_SECONDS = 86400
_RENEW_IF_OWNER_SCRIPT = """
local pending = redis.call(
    "XPENDING",
    KEYS[1],
    ARGV[1],
    ARGV[3],
    ARGV[3],
    1
)
if #pending ~= 1 or pending[1][2] ~= ARGV[2] then
    return 0
end
local renewed = redis.call(
    "XCLAIM",
    KEYS[1],
    ARGV[1],
    ARGV[2],
    0,
    ARGV[3],
    "IDLE",
    0,
    "JUSTID"
)
if #renewed ~= 1 or renewed[1] ~= ARGV[3] then
    return 0
end
return 1
""".strip()


class RedisStreamClient(Protocol):
    async def xgroup_create(self, *args: object, **kwargs: object) -> object: ...

    async def xadd(self, *args: object, **kwargs: object) -> str: ...

    async def xreadgroup(self, *args: object, **kwargs: object) -> object: ...

    async def xautoclaim(self, *args: object, **kwargs: object) -> object: ...

    async def eval(self, *args: object, **kwargs: object) -> object: ...

    async def xack(self, *args: object, **kwargs: object) -> int: ...

    async def xread(self, *args: object, **kwargs: object) -> object: ...

    async def expire(self, *args: object, **kwargs: object) -> object: ...

    async def aclose(self) -> None: ...


def _stream_messages(
    response: object,
) -> Sequence[tuple[str, Mapping[str, str]]]:
    if not isinstance(response, Sequence) or isinstance(response, (str, bytes)):
        raise TypeError("Redis stream response must be a sequence")
    messages: list[tuple[str, Mapping[str, str]]] = []
    for stream_entry in response:
        if not isinstance(stream_entry, Sequence) or len(stream_entry) != 2:
            raise TypeError("Redis stream entry must contain stream name and messages")
        raw_messages = stream_entry[1]
        if not isinstance(raw_messages, Sequence):
            raise TypeError("Redis stream messages must be a sequence")
        for raw_message in raw_messages:
            if not isinstance(raw_message, Sequence) or len(raw_message) != 2:
                raise TypeError("Redis message must contain id and fields")
            redis_id, fields = raw_message
            if not isinstance(redis_id, str) or not isinstance(fields, Mapping):
                raise TypeError("Redis message id and fields have invalid types")
            decoded = all(
                isinstance(key, str) and isinstance(value, str)
                for key, value in fields.items()
            )
            if not decoded:
                raise TypeError("Redis message fields must be decoded strings")
            messages.append((redis_id, fields))
    return messages


class RedisTaskBroker:
    def __init__(self, client: RedisStreamClient) -> None:
        self._client = client

    async def ensure_group(self) -> None:
        try:
            await self._client.xgroup_create(
                _GENERATION_STREAM,
                _GENERATION_GROUP,
                id="0-0",
                mkstream=True,
            )
        except ResponseError as exc:
            if "BUSYGROUP" not in str(exc):
                raise

    async def publish(self, message: TaskMessage) -> str:
        return await self._client.xadd(
            _GENERATION_STREAM,
            message.to_redis_fields(),
        )

    async def read(
        self, *, consumer: str, count: int, block_ms: int
    ) -> tuple[Delivery, ...]:
        response = await self._client.xreadgroup(
            _GENERATION_GROUP,
            consumer,
            streams={_GENERATION_STREAM: ">"},
            count=count,
            block=block_ms,
        )
        return self._deliveries(_stream_messages(response))

    async def autoclaim(
        self, *, consumer: str, min_idle_ms: int, count: int
    ) -> tuple[Delivery, ...]:
        response = await self._client.xautoclaim(
            _GENERATION_STREAM,
            _GENERATION_GROUP,
            consumer,
            min_idle_ms,
            start_id="0-0",
            count=count,
        )
        if not isinstance(response, Sequence) or len(response) < 2:
            raise TypeError("Redis XAUTOCLAIM response is malformed")
        messages = response[1]
        return self._deliveries(_stream_messages([(_GENERATION_STREAM, messages)]))

    async def renew(self, *, consumer: str, redis_id: str) -> bool:
        response = await self._client.eval(
            _RENEW_IF_OWNER_SCRIPT,
            1,
            _GENERATION_STREAM,
            _GENERATION_GROUP,
            consumer,
            redis_id,
        )
        if type(response) is not int or response not in {0, 1}:
            raise TypeError("Redis renewal response must be 0 or 1")
        return response == 1

    async def ack(self, redis_id: str) -> None:
        await self._client.xack(
            _GENERATION_STREAM,
            _GENERATION_GROUP,
            redis_id,
        )

    async def close(self) -> None:
        await self._client.aclose()

    @staticmethod
    def _deliveries(
        messages: Sequence[tuple[str, Mapping[str, str]]],
    ) -> tuple[Delivery, ...]:
        return tuple(
            Delivery(
                redis_id=redis_id,
                message=TaskMessage.from_redis_fields(fields),
            )
            for redis_id, fields in messages
        )


class RedisJobEventStream:
    def __init__(self, client: RedisStreamClient) -> None:
        self._client = client

    async def publish(self, event: TaskEvent) -> str:
        key = self._key(event.job_id)
        redis_id = await self._client.xadd(
            key,
            {
                "event_type": event.type.value,
                "data": json.dumps(event.data, ensure_ascii=False),
            },
            maxlen=_EVENT_MAX_LENGTH,
            approximate=True,
        )
        await self._client.expire(key, _EVENT_TTL_SECONDS)
        return redis_id

    async def read(
        self, *, job_id: str, after_id: str, block_ms: int
    ) -> tuple[ReplayableEvent, ...]:
        key = self._key(job_id)
        response = await self._client.xread(
            {key: after_id},
            count=_EVENT_MAX_LENGTH,
            block=block_ms,
        )
        return tuple(
            ReplayableEvent(
                redis_id=redis_id,
                event=TaskEvent(
                    job_id=job_id,
                    type=TaskEventType(fields["event_type"]),
                    data=self._event_data(fields["data"]),
                ),
            )
            for redis_id, fields in _stream_messages(response)
        )

    @staticmethod
    def _key(job_id: str) -> str:
        if not job_id:
            raise ValueError("job_id must not be empty")
        return f"{_EVENT_PREFIX}{job_id}"

    @staticmethod
    def _event_data(value: str) -> dict[str, Any]:
        parsed = json.loads(value)
        if not isinstance(parsed, dict) or not all(
            isinstance(key, str) for key in parsed
        ):
            raise ValueError("Redis job event data must be a JSON object")
        return parsed
