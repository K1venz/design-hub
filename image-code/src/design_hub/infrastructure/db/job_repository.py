from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from sqlalchemy.orm import selectinload

from design_hub.domain.enums import JobStatus, ModelName
from design_hub.domain.models import Brief, GeneratedImage, GenerationResult, JobRecord
from design_hub.infrastructure.db.models import GeneratedImageRow, GenerationJobRow
from design_hub.ports.job_repository import JobRepository


class SqlAlchemyJobRepository(JobRepository):
    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._session_factory = session_factory

    async def save_completed(
        self,
        *,
        job_id: str,
        user_id: str,
        brief: Brief,
        result: GenerationResult,
        project_id: int | None = None,
    ) -> str:
        async with self._session_factory() as session:
            row = GenerationJobRow(
                id=job_id,
                project_id=project_id,
                user_id=user_id,
                customer=brief.customer,
                subscene=brief.subscene.value,
                family=brief.family.value,
                tier=brief.tier.value,
                style=brief.style.value,
                category=brief.category.value,
                width=brief.size[0],
                height=brief.size[1],
                candidate_count=len(result.images),
                used_model=result.used_model.value,
                total_cost=result.total_cost,
                positive_prompt=result.job_prompt.positive,
                negative_prompt=result.job_prompt.negative,
                status=JobStatus.DONE.value,
                round_no=1,
                extra={},
            )
            row.images = [
                GeneratedImageRow(
                    url=img.url, seed=img.seed, latency_ms=img.latency_ms, cost=img.cost
                )
                for img in result.images
            ]
            session.add(row)
            await session.commit()
        return job_id

    async def get(self, job_id: str) -> JobRecord | None:
        async with self._session_factory() as session:
            stmt = (
                select(GenerationJobRow)
                .where(GenerationJobRow.id == job_id)
                .options(selectinload(GenerationJobRow.images))
            )
            row = (await session.execute(stmt)).scalar_one_or_none()
        if row is None:
            return None
        return JobRecord(
            id=row.id,
            user_id=row.user_id,
            customer=row.customer,
            used_model=ModelName(row.used_model),
            total_cost=row.total_cost,
            status=JobStatus(row.status),
            images=tuple(
                GeneratedImage(url=i.url, seed=i.seed, latency_ms=i.latency_ms, cost=i.cost)
                for i in row.images
            ),
        )
