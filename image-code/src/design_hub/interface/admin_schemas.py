"""模型配置后台 HTTP schema（边界翻译，WP-H / ISSUE-0057 配置大模型）。"""

from decimal import Decimal
from typing import Any

from pydantic import BaseModel, Field

from design_hub.ports.model_config_repository import ModelConfigRecord


class ModelConfigOut(BaseModel):
    """模型配置读出。**A1 密钥不入库：只回 api_key_env（环境变量名）、绝不回真 key**（验收⑦）。"""

    name: str
    unit_cost: Decimal
    enabled: bool
    extra: dict[str, Any]
    provider_type: str
    base_url: str
    model: str
    api_key_env: str  # 只是 env 变量名，真 key 留 server .env、永不出接口
    is_default: bool

    @classmethod
    def of(cls, r: ModelConfigRecord) -> "ModelConfigOut":
        return cls(
            name=r.name, unit_cost=r.unit_cost, enabled=r.enabled, extra=dict(r.extra),
            provider_type=r.provider_type, base_url=r.base_url, model=r.model,
            api_key_env=r.api_key_env, is_default=r.is_default,
        )


class ModelConfigCreate(BaseModel):
    """新增模型配置（POST /admin/models）。api_key_env=持有真 key 的 env 名（ops 在 .env 配）。"""

    name: str = Field(min_length=1)
    unit_cost: Decimal = Field(ge=0)
    provider_type: str = "openai_compat_image"
    base_url: str = ""
    model: str = ""
    api_key_env: str = ""
    enabled: bool = True

    def to_record(self) -> ModelConfigRecord:
        return ModelConfigRecord(
            name=self.name, unit_cost=self.unit_cost, enabled=self.enabled, extra={},
            provider_type=self.provider_type, base_url=self.base_url, model=self.model,
            api_key_env=self.api_key_env, is_default=False,  # 默认经 set_default 单独设
        )


class ModelConfigUpdate(BaseModel):
    """部分更新：仅传入的字段生效（None = 不改）。is_default 走 PUT …/default 端点（唯一性）。"""

    unit_cost: Decimal | None = Field(default=None, ge=0)
    enabled: bool | None = None
    extra: dict[str, Any] | None = None
    provider_type: str | None = None
    base_url: str | None = None
    model: str | None = None
    api_key_env: str | None = None
