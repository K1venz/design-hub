"""TaskQueue 的单进程内存实现（去 Redis/arq）。

enqueue 即在 API 进程内用 asyncio.create_task 后台运行命令；命令自己经
InMemoryEventBus 发布进度，/events 订阅同一实例。单实例部署；多副本换分布式适配器。
"""

import asyncio

from design_hub.ports.task_queue import GenerationCommand, TaskQueue


class InProcessTaskQueue(TaskQueue):
    def __init__(self) -> None:
        self._tasks: set[asyncio.Task[None]] = set()  # 持有引用防后台任务被 GC

    async def enqueue(self, *, job_id: str, command: GenerationCommand) -> None:
        task = asyncio.create_task(command.run(job_id))
        self._tasks.add(task)
        task.add_done_callback(self._on_done)

    def _on_done(self, task: asyncio.Task[None]) -> None:
        self._tasks.discard(task)
        # 取出异常防 asyncio "Task exception never retrieved"（命令已发布 task_failed）
        if not task.cancelled():
            task.exception()
