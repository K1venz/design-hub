"""模型配置后台 HTTP schema（边界翻译，WP-H）。"""

from decimal import Decimal
from typing import Any

from pydantic import BaseModel, Field

from design_hub.ports.model_config_repository import ModelConfigRecord


class ModelConfigOut(BaseModel):
    name: str
    unit_cost: Decimal
    enabled: bool
    extra: dict[str, Any]

    @classmethod
    def of(cls, r: ModelConfigRecord) -> "ModelConfigOut":
        return cls(name=r.name, unit_cost=r.unit_cost, enabled=r.enabled, extra=dict(r.extra))


class ModelConfigUpdate(BaseModel):
    """部分更新：仅传入的字段生效（None = 不改）。"""

    unit_cost: Decimal | None = Field(default=None, ge=0)
    enabled: bool | None = None
    extra: dict[str, Any] | None = None
