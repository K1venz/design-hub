import re
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Protocol

_SAFE_KEY_PART = re.compile(r"[A-Za-z0-9._-]{1,128}")

_ACQUIRE_SCRIPT = """-- acquire
local key = KEYS[1]
local member = ARGV[1]
local now = tonumber(ARGV[2])
local expires = tonumber(ARGV[3])
local limit = tonumber(ARGV[4])
redis.call('ZREMRANGEBYSCORE', key, '-inf', now)
if redis.call('ZSCORE', key, member) then
  redis.call('ZADD', key, expires, member)
  return 1
end
if redis.call('ZCARD', key) >= limit then
  return 0
end
redis.call('ZADD', key, expires, member)
return 1
"""

_REFRESH_SCRIPT = """-- refresh
local key = KEYS[1]
local member = ARGV[1]
local expires = tonumber(ARGV[2])
if not redis.call('ZSCORE', key, member) then
  return 0
end
redis.call('ZADD', key, expires, member)
return 1
"""

_RELEASE_SCRIPT = """-- release
return redis.call('ZREM', KEYS[1], ARGV[1])
"""


class RedisEvalClient(Protocol):
    async def eval(
        self, script: str, numkeys: int, *keys_and_args: object
    ) -> object: ...


def _system_clock_ms() -> int:
    return int(time.time() * 1000)


@dataclass(frozen=True)
class RedisProviderSlots:
    client: RedisEvalClient
    provider: str
    tier: str
    limit: int
    lease_seconds: int
    clock_ms: Callable[[], int] = field(default=_system_clock_ms)

    def __post_init__(self) -> None:
        if _SAFE_KEY_PART.fullmatch(self.provider) is None:
            raise ValueError("provider contains unsafe Redis key characters")
        if _SAFE_KEY_PART.fullmatch(self.tier) is None:
            raise ValueError("tier contains unsafe Redis key characters")
        if self.limit <= 0 or self.lease_seconds <= 0:
            raise ValueError("slot limit and lease_seconds must be positive")

    async def acquire(self, *, worker_id: str, item_id: str) -> bool:
        now = self.clock_ms()
        result = await self.client.eval(
            _ACQUIRE_SCRIPT,
            1,
            self._key,
            self._member(worker_id, item_id),
            now,
            now + self.lease_seconds * 1000,
            self.limit,
        )
        return bool(result)

    async def refresh(self, *, worker_id: str, item_id: str) -> bool:
        now = self.clock_ms()
        result = await self.client.eval(
            _REFRESH_SCRIPT,
            1,
            self._key,
            self._member(worker_id, item_id),
            now + self.lease_seconds * 1000,
        )
        return bool(result)

    async def release(self, *, worker_id: str, item_id: str) -> bool:
        result = await self.client.eval(
            _RELEASE_SCRIPT,
            1,
            self._key,
            self._member(worker_id, item_id),
        )
        return bool(result)

    @property
    def _key(self) -> str:
        return f"design-hub:provider-slots:{self.provider}:{self.tier}"

    @staticmethod
    def _member(worker_id: str, item_id: str) -> str:
        if _SAFE_KEY_PART.fullmatch(worker_id) is None:
            raise ValueError("worker_id contains unsafe Redis member characters")
        if _SAFE_KEY_PART.fullmatch(item_id) is None:
            raise ValueError("item_id contains unsafe Redis member characters")
        return f"{worker_id}:{item_id}"
