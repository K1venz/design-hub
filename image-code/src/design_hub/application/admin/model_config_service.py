"""模型配置后台用例（WP-H，PRD §3.5 / §6.3.3 仅管理者）。

SRP：CRUD model_config + 产出"单价注入映射"供 composition 构造 Provider。
单价真实来源于 DB，替换 composition 写死的 Mock 价；DB 缺失的模型仍回落 Mock（兜底）。
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from decimal import Decimal
from typing import Any

from design_hub.domain.enums import ModelName
from design_hub.ports.model_config_repository import ModelConfigRecord, ModelConfigRepository


@dataclass
class ModelConfigService:
    """模型配置用例（依赖 ModelConfigRepository，DIP）。"""

    repo: ModelConfigRepository

    async def list(self) -> list[ModelConfigRecord]:
        return await self.repo.list_all()

    async def update(
        self,
        *,
        actor_id: int,
        name: str,
        unit_cost: Decimal | None = None,
        enabled: bool | None = None,
        extra: Mapping[str, Any] | None = None,
        provider_type: str | None = None,
        base_url: str | None = None,
        model: str | None = None,
        api_key_env: str | None = None,
    ) -> ModelConfigRecord:
        # 非 I/O 业务校验：fail-fast（单价不得为负）
        if unit_cost is not None and unit_cost < 0:
            raise ValueError("单价不能为负")
        return await self.repo.update(
            actor_id=actor_id, name=name,
            unit_cost=unit_cost, enabled=enabled, extra=extra,
            provider_type=provider_type, base_url=base_url, model=model,
            api_key_env=api_key_env,
        )

    async def create(
        self,
        *,
        actor_id: int,
        record: ModelConfigRecord,
    ) -> ModelConfigRecord:
        # ISSUE-0057：新增一个可用模型配置（A1 密钥不入库、record.api_key_env 只存 env 名）。
        if record.unit_cost < 0:
            raise ValueError("单价不能为负")
        if not record.name.strip():
            raise ValueError("模型名不能为空")
        return await self.repo.create(actor_id=actor_id, record=record)

    async def delete(self, *, actor_id: int, name: str) -> None:
        await self.repo.delete(actor_id=actor_id, name=name)

    async def set_default(
        self,
        *,
        actor_id: int,
        name: str,
    ) -> ModelConfigRecord:
        """设为默认出图模型（唯一性由 repo 事务保证）。备用渠道切换=改默认，治 0056 单点。"""
        return await self.repo.set_default(actor_id=actor_id, name=name)

    async def seed_defaults(self, defaults: Sequence[ModelConfigRecord]) -> None:
        await self.repo.seed_defaults(defaults)

    async def unit_cost_map(self) -> dict[ModelName, Decimal]:
        """单价映射（按 ModelName），供 composition 注入 Provider，替换写死的 Mock 价。

        只取 name 命中 ModelName 枚举的行（未命中的留给 Mock 兜底）。单价 ⊥ enabled：
        enabled 是模型可用性，归路由层（当前路由用静态表、暂未消费 model_config，属后续）。
        """
        valid = {m.value: m for m in ModelName}
        return {
            valid[r.name]: r.unit_cost
            for r in await self.repo.list_all()
            if r.name in valid
        }
