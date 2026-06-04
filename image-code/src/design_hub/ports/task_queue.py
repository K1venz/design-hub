from abc import ABC, abstractmethod


class GenerationCommand(ABC):
    """一次异步出图任务的自包含执行单元（命令模式）。

    每个命令自己负责：发布进度事件、生成、持久化。队列只调度，不认识具体流程。
    """

    @abstractmethod
    async def run(self, job_id: str) -> None:
        ...


class TaskQueue(ABC):
    """出图任务入队端口（DIP）；单进程实现 InProcessTaskQueue，多副本可换分布式适配器。"""

    @abstractmethod
    async def enqueue(self, *, job_id: str, command: GenerationCommand) -> None:
        ...
