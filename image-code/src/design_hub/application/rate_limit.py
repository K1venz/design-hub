"""per-user 频控（安全加固 A-4，审计 #583）：计费端点防刷。

滑动窗口 + in-flight 双闸，in-memory 实现（本仓无 Redis 铁律；单机单进程足够，
重启清零可接受——这是频控不是配额，配额归 gate 7.D 积分制）。超限 → RateLimited → 429。
"""

import time
from collections import deque
from dataclasses import dataclass, field

from design_hub.ports.task_queue import GenerationCommand

_MAX_PER_MINUTE = 5  # 每用户每分钟最多提交的出图单数（计费动作速率闸）
_MAX_IN_FLIGHT = 2  # 每用户同时进行中的出图单上限（防长任务堆叠占满并发/上游）
_WINDOW_SECONDS = 60.0


class RateLimited(Exception):
    """频率/并发超限（边界概念，不进 domain；app.py 映射 429）。"""


@dataclass
class UserRateLimiter:
    """per-user 滑动窗口 + in-flight 计数。acquire 在入队前调、超限 fail-fast。"""

    max_per_minute: int = _MAX_PER_MINUTE
    max_in_flight: int = _MAX_IN_FLIGHT
    _windows: dict[str, deque[float]] = field(default_factory=dict)
    _in_flight: dict[str, int] = field(default_factory=dict)

    def acquire(self, user_id: str) -> None:
        now = time.monotonic()
        window = self._windows.setdefault(user_id, deque())
        while window and now - window[0] > _WINDOW_SECONDS:
            window.popleft()
        if len(window) >= self.max_per_minute:
            raise RateLimited(
                f"出图请求过于频繁：每分钟最多 {self.max_per_minute} 单，请稍后再试"
            )
        if self._in_flight.get(user_id, 0) >= self.max_in_flight:
            raise RateLimited(
                f"进行中的出图任务已达上限（{self.max_in_flight} 单），请等待完成后再提交"
            )
        window.append(now)
        self._in_flight[user_id] = self._in_flight.get(user_id, 0) + 1

    def release(self, user_id: str) -> None:
        count = self._in_flight.get(user_id, 0)
        if count <= 1:
            self._in_flight.pop(user_id, None)
        else:
            self._in_flight[user_id] = count - 1


@dataclass
class ThrottledCommand(GenerationCommand):
    """命令包装：任务结束（成败均）归还 in-flight 名额，零侵入既有命令。"""

    inner: GenerationCommand
    limiter: UserRateLimiter
    user_id: str

    async def run(self, job_id: str) -> None:
        try:
            await self.inner.run(job_id)
        finally:
            self.limiter.release(self.user_id)
