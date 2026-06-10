from datetime import UTC, datetime

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from design_hub.domain.models import ListingJobOutcome
from design_hub.infrastructure.db.models import (
    ListingImageRow,
    ListingJobInputRow,
    ListingJobRow,
)
from design_hub.ports.listing_history import ListingHistory


class SqlAlchemyListingHistory(ListingHistory):
    """ListingHistory 的 DB 写实现（ISSUE-0030）：落 listing_job + 每张 listing_image +
    每张输入 listing_job_input。与海报流 JobRepository 彻底分开。"""

    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._session_factory = session_factory

    async def record(self, outcome: ListingJobOutcome) -> None:
        async with self._session_factory() as session:
            row = ListingJobRow(
                id=outcome.job_id,
                user_id=outcome.user_id,
                prompt=outcome.prompt,
                modifiers=dict(outcome.modifiers),
                platform=outcome.modifiers.get("platform"),
                ratio=outcome.ratio,
                size=outcome.size,
                n=outcome.n,
                status=outcome.status,
                total_cost=outcome.total_cost,
                error=outcome.error,
                clone_mode=outcome.clone_mode,
                completed_at=datetime.now(UTC),
            )
            row.images = [
                ListingImageRow(
                    image_key=im.image_key, seed=im.seed, cost=im.cost,
                    status=im.status, image_type=im.image_type
                )
                for im in outcome.images
            ]
            roles = outcome.input_roles or (None,) * len(outcome.upload_keys)
            row.inputs = [
                ListingJobInputRow(upload_key=key, role=role, ord=i)
                for i, (key, role) in enumerate(zip(outcome.upload_keys, roles, strict=True))
            ]
            session.add(row)
            await session.commit()
