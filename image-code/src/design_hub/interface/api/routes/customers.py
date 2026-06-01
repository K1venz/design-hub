from fastapi import APIRouter, HTTPException

from design_hub.interface.api.project_deps import CustomerServiceDep
from design_hub.interface.project_schemas import CustomerCreate, CustomerOut

router = APIRouter(prefix="/customers", tags=["customers"])


@router.post("", response_model=CustomerOut)
async def create_customer(body: CustomerCreate, svc: CustomerServiceDep) -> CustomerOut:
    record = await svc.create(
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
async def list_customers(svc: CustomerServiceDep) -> list[CustomerOut]:
    return [CustomerOut.of(r) for r in await svc.list()]


@router.get("/{customer_id}", response_model=CustomerOut)
async def get_customer(customer_id: int, svc: CustomerServiceDep) -> CustomerOut:
    record = await svc.get(customer_id)
    if record is None:
        raise HTTPException(status_code=404, detail="customer not found")
    return CustomerOut.of(record)
