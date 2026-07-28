import asyncio
from collections.abc import Callable
from typing import Any

from design_hub.infrastructure.queue.redis_slots import RedisProviderSlots


class _FakeRedis:
    def __init__(self) -> None:
        self.sets: dict[str, dict[str, int]] = {}

    async def eval(
        self, script: str, numkeys: int, *keys_and_args: object
    ) -> Any:
        assert numkeys == 1
        key = str(keys_and_args[0])
        args = [str(value) for value in keys_and_args[1:]]
        entries = self.sets.setdefault(key, {})
        if script.startswith("-- acquire"):
            member, now, expires, limit = args
            now_ms = int(now)
            for stale in [name for name, score in entries.items() if score <= now_ms]:
                del entries[stale]
            if member in entries:
                entries[member] = int(expires)
                return 1
            if len(entries) >= int(limit):
                return 0
            entries[member] = int(expires)
            return 1
        if script.startswith("-- refresh"):
            member, expires = args
            if member not in entries:
                return 0
            entries[member] = int(expires)
            return 1
        if script.startswith("-- release"):
            member = args[0]
            return 1 if entries.pop(member, None) is not None else 0
        raise AssertionError("unknown Lua script")


def _clock(values: list[int]) -> Callable[[], int]:
    def now() -> int:
        return values[0]

    return now


def test_global_limit_is_shared_between_worker_instances() -> None:
    async def run() -> None:
        redis = _FakeRedis()
        now = [1_000]
        first = RedisProviderSlots(
            redis,
            provider="gpt-image-2",
            tier="standard",
            limit=2,
            lease_seconds=30,
            clock_ms=_clock(now),
        )
        second = RedisProviderSlots(
            redis,
            provider="gpt-image-2",
            tier="standard",
            limit=2,
            lease_seconds=30,
            clock_ms=_clock(now),
        )

        assert await first.acquire(worker_id="worker-a", item_id="item-1") is True
        assert await second.acquire(worker_id="worker-b", item_id="item-2") is True
        assert await first.acquire(worker_id="worker-a", item_id="item-3") is False

    asyncio.run(run())


def test_expired_lease_frees_capacity_and_only_owner_member_releases() -> None:
    async def run() -> None:
        redis = _FakeRedis()
        now = [1_000]
        slots = RedisProviderSlots(
            redis,
            provider="gpt-image-2",
            tier="standard",
            limit=1,
            lease_seconds=30,
            clock_ms=_clock(now),
        )
        assert await slots.acquire(worker_id="worker-a", item_id="item-1") is True
        assert await slots.release(worker_id="worker-b", item_id="item-1") is False
        assert await slots.acquire(worker_id="worker-b", item_id="item-2") is False

        now[0] = 31_001
        assert await slots.acquire(worker_id="worker-b", item_id="item-2") is True

    asyncio.run(run())


def test_refresh_extends_owned_lease_and_missing_member_fails() -> None:
    async def run() -> None:
        redis = _FakeRedis()
        now = [1_000]
        slots = RedisProviderSlots(
            redis,
            provider="gpt-image-2",
            tier="standard",
            limit=1,
            lease_seconds=30,
            clock_ms=_clock(now),
        )
        assert await slots.refresh(worker_id="worker-a", item_id="missing") is False
        assert await slots.acquire(worker_id="worker-a", item_id="item-1") is True
        now[0] = 20_000
        assert await slots.refresh(worker_id="worker-a", item_id="item-1") is True
        now[0] = 40_000
        assert await slots.acquire(worker_id="worker-b", item_id="item-2") is False

    asyncio.run(run())


def test_standard_and_4k_use_isolated_slot_pools() -> None:
    async def run() -> None:
        redis = _FakeRedis()
        now = [1_000]
        standard = RedisProviderSlots(
            redis,
            provider="gpt-image-2",
            tier="standard",
            limit=1,
            lease_seconds=30,
            clock_ms=_clock(now),
        )
        four_k = RedisProviderSlots(
            redis,
            provider="gpt-image-2",
            tier="4k",
            limit=1,
            lease_seconds=30,
            clock_ms=_clock(now),
        )
        assert await standard.acquire(worker_id="worker-a", item_id="item-1") is True
        assert await four_k.acquire(worker_id="worker-a", item_id="item-2") is True

    asyncio.run(run())
