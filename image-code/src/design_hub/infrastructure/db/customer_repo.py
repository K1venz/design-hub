from collections.abc import Sequence

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from design_hub.domain.models import CustomerRecord
from design_hub.infrastructure.db.models import Customer
from design_hub.ports.repositories import CustomerRepository


def _to_record(row: Customer) -> CustomerRecord:
    return CustomerRecord(
        id=row.id,
        name=row.name,
        contact=row.contact,
        industry=row.industry,
        brand_color=row.brand_color,
        common_styles=tuple(row.common_styles),
        common_taboos=tuple(row.common_taboos),
        common_sizes=tuple(row.common_sizes),
    )


class SqlAlchemyCustomerRepository(CustomerRepository):
    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._session_factory = session_factory

    async def create(
        self,
        *,
        name: str,
        contact: str | None = None,
        industry: str | None = None,
        brand_color: str | None = None,
        common_styles: Sequence[str] = (),
        common_taboos: Sequence[str] = (),
        common_sizes: Sequence[str] = (),
    ) -> CustomerRecord:
        async with self._session_factory() as session:
            row = Customer(
                name=name,
                contact=contact,
                industry=industry,
                brand_color=brand_color,
                common_styles=list(common_styles),
                common_taboos=list(common_taboos),
                common_sizes=list(common_sizes),
            )
            session.add(row)
            await session.commit()
            await session.refresh(row)
            return _to_record(row)

    async def get(self, customer_id: int) -> CustomerRecord | None:
        async with self._session_factory() as session:
            row = await session.get(Customer, customer_id)
            return _to_record(row) if row is not None else None

    async def list(self) -> list[CustomerRecord]:
        async with self._session_factory() as session:
            rows = (await session.execute(select(Customer).order_by(Customer.id))).scalars().all()
            return [_to_record(r) for r in rows]
