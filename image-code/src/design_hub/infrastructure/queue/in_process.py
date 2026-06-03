"""TaskQueue 的单进程内存实现（去 Redis/arq）。

enqueue 即在 API 进程内用 asyncio.create_task 后台运行 GenerationTaskRunner.run；
进度事件经 runner 注入的 InMemoryEventBus 发布，/events 订阅同一实例。
适用单实例部署；多副本需回退分布式队列（端口不变，换适配器即可，LSP/DIP）。
"""

import asyncio

from design_hub.application.task_runner import GenerationTaskRunner
from design_hub.domain.models import Brief
from design_hub.ports.task_queue import TaskQueue


class InProcessTaskQueue(TaskQueue):
    def __init__(self, runner: GenerationTaskRunner) -> None:
        self._runner = runner
        self._tasks: set[asyncio.Task[str]] = set()  # 持有引用防后台任务被 GC

    async def enqueue(self, *, job_id: str, brief: Brief, user_id: str) -> None:
        task = asyncio.create_task(
            self._runner.run(job_id=job_id, brief=brief, user_id=user_id)
        )
        self._tasks.add(task)
        task.add_done_callback(self._on_done)

    def _on_done(self, task: asyncio.Task[str]) -> None:
        self._tasks.discard(task)
        # 取出异常防 asyncio "Task exception never retrieved"（runner 已发布 task_failed）
        if not task.cancelled():
            task.exception()
