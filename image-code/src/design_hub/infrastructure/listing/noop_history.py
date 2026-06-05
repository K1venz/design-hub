from design_hub.domain.models import ListingJobOutcome
from design_hub.ports.listing_history import ListingHistory


class NoOpListingHistory(ListingHistory):
    """不持久化的占位实现（dev/CI 全 Mock 装配用；生产装配 SqlAlchemyListingHistory）。"""

    async def record(self, outcome: ListingJobOutcome) -> None:
        return None
