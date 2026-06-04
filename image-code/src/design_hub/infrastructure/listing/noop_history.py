from design_hub.domain.models import ListingResult
from design_hub.ports.listing_history import ListingHistory


class NoOpListingHistory(ListingHistory):
    """MVP：不持久化 listing 历史（服务器空间充足后换 DB 实现，业务零改动）。"""

    async def record(self, *, user_id: str, result: ListingResult) -> None:
        return None
