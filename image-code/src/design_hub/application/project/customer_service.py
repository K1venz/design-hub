from collections.abc import Sequence
from dataclasses import dataclass

from design_hub.domain.models import CustomerRecord
from design_hub.ports.repositories import CustomerRepository


@dataclass
class CustomerService:
    """客户档案用例（SRP）：依赖 CustomerRepository 端口（DIP）。"""

    customers: CustomerRepository

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
        if not name.strip():
            raise ValueError("客户名称不能为空")
        return await self.customers.create(
            name=name,
            contact=contact,
            industry=industry,
            brand_color=brand_color,
            common_styles=common_styles,
            common_taboos=common_taboos,
            common_sizes=common_sizes,
        )

    async def get(self, customer_id: int) -> CustomerRecord | None:
        return await self.customers.get(customer_id)

    async def list(self) -> list[CustomerRecord]:
        return await self.customers.list()
