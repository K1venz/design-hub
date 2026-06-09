from fastapi import APIRouter

from design_hub.domain.errors import NotFoundError
from design_hub.interface.api.deps import CurrentUserDep
from design_hub.interface.api.project_deps import CustomerServiceDep
from design_hub.interface.project_schemas import CustomerCreate, CustomerOut

router = APIRouter(prefix="/customers", tags=["customers"])


@router.post("", response_model=CustomerOut)
async def create_customer(
    body: CustomerCreate, svc: CustomerServiceDep, user: CurrentUserDep
) -> CustomerOut:
    record = await svc.create(
        user_id=user.user_id,
        name=body.name,
        contact=body.contact,
        industry=body.industry,
        brand_color=body.brand_color,
        common_styles=body.common_styles,
        common_taboos=body.common_taboos,
        common_sizes=body.common_sizes,
    )
    return CustomerOut.of(record)


@router.get("", response_model=list[CustomerOut])
async def list_customers(svc: CustomerServiceDep, user: CurrentUserDep) -> list[CustomerOut]:
    return [CustomerOut.of(r) for r in await svc.list(user.user_id)]


@router.get("/{customer_id}", response_model=CustomerOut)
async def get_customer(
    customer_id: int, svc: CustomerServiceDep, user: CurrentUserDep
) -> CustomerOut:
    # 仅本人；非本人 / 不存在 → 404（anti-enum，不泄露存在性，ISSUE-0041/0032）
    record = await svc.get(customer_id, user.user_id)
    if record is None:
        raise NotFoundError(f"客户不存在或无权访问：{customer_id}")
    return CustomerOut.of(record)
