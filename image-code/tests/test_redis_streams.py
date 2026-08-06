import asyncio
from datetime import UTC, datetime
from typing import Any

import pytest
from redis.exceptions import ResponseError

from design_hub.domain.tasking import InvalidTaskMessage, OperationType, TaskMessage
from design_hub.infrastructure.queue.redis_streams import RedisTaskBroker


class _FakeRedis:
    def __init__(self) -> None:
        self.calls: list[tuple[str, tuple[object, ...], dict[str, object]]] = []
        self.read_result: object = []
        self.claim_result: object = ("0-0", [], [])
        self.renew_result: object = []
        self.group_error: ResponseError | None = None
        self.closed = False

    async def xgroup_create(self, *args: object, **kwargs: object) -> None:
        self.calls.append(("xgroup_create", args, kwargs))
        if self.group_error is not None:
            raise self.group_error

    async def xadd(self, *args: object, **kwargs: object) -> str:
        self.calls.append(("xadd", args, kwargs))
        return "10-0"

    async def xreadgroup(self, *args: object, **kwargs: object) -> Any:
        self.calls.append(("xreadgroup", args, kwargs))
        return self.read_result

    async def xautoclaim(self, *args: object, **kwargs: object) -> Any:
        self.calls.append(("xautoclaim", args, kwargs))
        return self.claim_result

    async def xclaim(self, *args: object, **kwargs: object) -> Any:
        self.calls.append(("xclaim", args, kwargs))
        return self.renew_result

    async def xack(self, *args: object, **kwargs: object) -> int:
        self.calls.append(("xack", args, kwargs))
        return 1

    async def aclose(self) -> None:
        self.closed = True


def _message() -> TaskMessage:
    return TaskMessage(
        schema_version=1,
        message_id="message-1",
        trace_id="trace-1",
        request_id="request-1",
        job_id="job-1",
        item_id="item-1",
        operation_id="operation-1",
        operation_type=OperationType.GENERATE_IMAGE,
        user_id="1",
        created_at=datetime(2026, 7, 28, tzinfo=UTC),
    )


def test_group_setup_publish_read_ack_and_close() -> None:
    async def run() -> None:
        redis = _FakeRedis()
        broker = RedisTaskBroker(redis)
        await broker.ensure_group()
        assert await broker.publish(_message()) == "10-0"
        redis.read_result = [
            (
                "design-hub:generation:v1",
                [("10-0", _message().to_redis_fields())],
            )
        ]
        deliveries = await broker.read(consumer="worker-1", count=10, block_ms=5000)
        assert deliveries[0].redis_id == "10-0"
        assert deliveries[0].message == _message()
        await broker.ack("10-0")
        await broker.close()

        assert redis.calls[0] == (
            "xgroup_create",
            ("design-hub:generation:v1", "generation-workers-v1"),
            {"id": "0-0", "mkstream": True},
        )
        assert redis.calls[1][0] == "xadd"
        assert redis.calls[2] == (
            "xreadgroup",
            ("generation-workers-v1", "worker-1"),
            {"streams": {"design-hub:generation:v1": ">"}, "count": 10, "block": 5000},
        )
        assert redis.calls[3] == (
            "xack",
            ("design-hub:generation:v1", "generation-workers-v1", "10-0"),
            {},
        )
        assert redis.closed is True

    asyncio.run(run())


def test_group_setup_ignores_only_busygroup() -> None:
    async def run() -> None:
        redis = _FakeRedis()
        broker = RedisTaskBroker(redis)
        redis.group_error = ResponseError("BUSYGROUP Consumer Group name already exists")
        await broker.ensure_group()
        redis.group_error = ResponseError("NOPERM denied")
        with pytest.raises(ResponseError, match="NOPERM"):
            await broker.ensure_group()

    asyncio.run(run())


def test_autoclaim_parses_pending_delivery() -> None:
    async def run() -> None:
        redis = _FakeRedis()
        redis.claim_result = (
            "20-0",
            [("11-0", _message().to_redis_fields())],
            [],
        )
        broker = RedisTaskBroker(redis)

        deliveries = await broker.autoclaim(
            consumer="worker-2", min_idle_ms=30000, count=5
        )

        assert deliveries[0].redis_id == "11-0"
        assert deliveries[0].message.item_id == "item-1"
        assert redis.calls[0] == (
            "xautoclaim",
            ("design-hub:generation:v1", "generation-workers-v1", "worker-2", 30000),
            {"start_id": "0-0", "count": 5},
        )

    asyncio.run(run())


def test_malformed_delivery_fails_without_ack() -> None:
    async def run() -> None:
        redis = _FakeRedis()
        fields = _message().to_redis_fields()
        fields["final_prompt"] = "must never be in Redis"
        redis.read_result = [("design-hub:generation:v1", [("12-0", fields)])]
        broker = RedisTaskBroker(redis)

        with pytest.raises(InvalidTaskMessage):
            await broker.read(consumer="worker-1", count=1, block_ms=1)

        assert all(call[0] != "xack" for call in redis.calls)

    asyncio.run(run())


def test_renew_resets_pending_delivery_idle_without_incrementing_retries() -> None:
    async def run() -> None:
        redis = _FakeRedis()
        redis.renew_result = ["10-0"]
        broker = RedisTaskBroker(redis)

        assert await broker.renew(consumer="worker-1", redis_id="10-0") is True
        assert redis.calls == [
            (
                "xclaim",
                (
                    "design-hub:generation:v1",
                    "generation-workers-v1",
                    "worker-1",
                    0,
                    ("10-0",),
                ),
                {"idle": 0, "justid": True},
            )
        ]

    asyncio.run(run())


def test_renew_reports_lost_delivery_and_rejects_malformed_response() -> None:
    async def run() -> None:
        redis = _FakeRedis()
        broker = RedisTaskBroker(redis)
        assert await broker.renew(consumer="worker-1", redis_id="10-0") is False

        redis.renew_result = [1]
        with pytest.raises(TypeError, match="XCLAIM response"):
            await broker.renew(consumer="worker-1", redis_id="10-0")

    asyncio.run(run())
