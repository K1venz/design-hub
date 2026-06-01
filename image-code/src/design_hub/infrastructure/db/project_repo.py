from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from design_hub.domain.enums import ProjectStatus
from design_hub.domain.errors import DomainError
from design_hub.domain.models import ProjectRecord
from design_hub.infrastructure.db.models import Project
from design_hub.ports.repositories import ProjectRepository


def _to_record(row: Project) -> ProjectRecord:
    return ProjectRecord(
        id=row.id,
        customer_id=row.customer_id,
        name=row.name,
        status=ProjectStatus(row.status),
        current_round=row.current_round,
    )


class SqlAlchemyProjectRepository(ProjectRepository):
    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._session_factory = session_factory

    async def create(self, *, customer_id: int, name: str) -> ProjectRecord:
        async with self._session_factory() as session:
            row = Project(
                customer_id=customer_id,
                name=name,
                status=ProjectStatus.REQUIREMENT.value,
                current_round=1,
            )
            session.add(row)
            await session.commit()
            await session.refresh(row)
            return _to_record(row)

    async def get(self, project_id: int) -> ProjectRecord | None:
        async with self._session_factory() as session:
            row = await session.get(Project, project_id)
            return _to_record(row) if row is not None else None

    async def list(self, *, customer_id: int | None = None) -> list[ProjectRecord]:
        async with self._session_factory() as session:
            stmt = select(Project).order_by(Project.id)
            if customer_id is not None:
                stmt = stmt.where(Project.customer_id == customer_id)
            rows = (await session.execute(stmt)).scalars().all()
            return [_to_record(r) for r in rows]

    async def set_status(self, project_id: int, status: ProjectStatus) -> ProjectRecord:
        async with self._session_factory() as session:
            row = await session.get(Project, project_id)
            if row is None:
                raise DomainError(f"project {project_id} not found")
            # 进入「客户审稿→设计中」即改稿循环，轮次递增（PRD §4.1）
            if (
                ProjectStatus(row.status) is ProjectStatus.REVIEW
                and status is ProjectStatus.DESIGNING
            ):
                row.current_round += 1
            row.status = status.value
            await session.commit()
            await session.refresh(row)
            return _to_record(row)
