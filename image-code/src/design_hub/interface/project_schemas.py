from pydantic import BaseModel, Field

from design_hub.domain.models import CustomerRecord


class CustomerCreate(BaseModel):
    name: str = Field(min_length=1)
    contact: str | None = None
    industry: str | None = None
    brand_color: str | None = None
    common_styles: list[str] = Field(default_factory=list)
    common_taboos: list[str] = Field(default_factory=list)
    common_sizes: list[str] = Field(default_factory=list)


class CustomerOut(BaseModel):
    id: int
    name: str
    contact: str | None
    industry: str | None
    brand_color: str | None
    common_styles: list[str]
    common_taboos: list[str]
    common_sizes: list[str]

    @classmethod
    def of(cls, r: CustomerRecord) -> "CustomerOut":
        return cls(
            id=r.id, name=r.name, contact=r.contact, industry=r.industry,
            brand_color=r.brand_color, common_styles=list(r.common_styles),
            common_taboos=list(r.common_taboos), common_sizes=list(r.common_sizes),
        )
