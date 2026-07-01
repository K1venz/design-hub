from abc import ABC, abstractmethod
from datetime import timedelta
from decimal import Decimal

from design_hub.domain.models import ListingJobImage, ListingJobStart


class ListingHistory(ABC):
    """listing 出图历史持久化端口（写侧，两阶段落库 ISSUE-0047/0030）。

    进行中单在 DB 即有行、可查、可增量：
      1) start        —— 入队开跑即落一行（status='生成中'、completed_at 空），带输入产品图；
      2) add_images   —— 每批出图（成功张 + 失败张）增量写 listing_image；
      3) finalize     —— 全部结束改 status（完成|部分完成|失败）+ 补 completed_at。
    与海报流 JobRepository 彻底分开。OSS 化只换 image_store，不动本端口。
    """

    @abstractmethod
    async def start(self, job: ListingJobStart) -> None:
        """建一条 listing_job 行（status='生成中'）+ 全部输入产品图行。"""
        ...

    @abstractmethod
    async def add_images(self, job_id: str, images: tuple[ListingJobImage, ...]) -> None:
        """增量落该 job 的候选图（成功张带产物、失败张 status='失败' 留痕）。空批为 no-op。"""
        ...

    @abstractmethod
    async def finalize(
        self, job_id: str, *, status: str, total_cost: Decimal, error: str | None
    ) -> None:
        """终态：改 status + total_cost + error，补 completed_at。行须已由 start 建出。"""
        ...

    @abstractmethod
    async def reap_stale(self, *, older_than: timedelta, error: str) -> int:
        """启动扫尾（Finding B）：把超龄未终态的 status='生成中' 僵尸行兜底改'失败'。

        单进程 asyncio 出图，进程崩/部署重启会杀掉在飞任务而不跑 finalize，留永久
        「生成中」死单（SSE 永久转圈、霸占最近一单）。扫 created_at 早于 now-older_than
        的行、UPDATE 成失败 + 标 error + 补 completed_at；纯现列 query+update，无迁移。
        返回扫改行数。
        """
        ...
