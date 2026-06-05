from abc import ABC, abstractmethod

from design_hub.domain.models import ListingJobOutcome


class ListingHistory(ABC):
    """listing 出图历史持久化端口（写侧）。

    MVP 曾绑 NoOp 不存；ISSUE-0030 起绑 DB 实现，落 listing_job + listing_image +
    listing_job_input（与海报流的 JobRepository 彻底分开）。OSS 化只换 image_store，不动本端口。
    """

    @abstractmethod
    async def record(self, outcome: ListingJobOutcome) -> None:
        ...
