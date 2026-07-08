"""模型配置仓储端口（DIP）。WP-H：单价/启停热更的持久化抽象。

独立端口文件（不并入 ports/repositories.py，避免多 agent 共写冲突）。
单价真实来源 = model_config 表；composition 据此注入 Provider，替换写死的 Mock 价。
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from decimal import Decimal
from typing import Any


@dataclass(frozen=True)
class ModelConfigRecord:
    """模型配置读模型。name 为自由字符串主键（与 ModelName 枚举值对齐但不强绑）。

    配置大模型（ISSUE-0057）：provider_type/base_url/model/api_key_env/is_default 描述一个
    可用出图模型的连接（A1 密钥不入库、仅存 env 名）。新字段有默认值，兼容旧构造。
    """

    name: str
    unit_cost: Decimal
    enabled: bool
    extra: dict[str, Any]
    provider_type: str = "openai_compat_image"
    base_url: str = ""
    model: str = ""
    api_key_env: str = ""
    is_default: bool = False


class ModelConfigRepository(ABC):
    """模型配置仓储端口。写 model_config 行不算 schema 变更（表已存在）。"""

    @abstractmethod
    async def list_all(self) -> list[ModelConfigRecord]:
        ...

    @abstractmethod
    async def get(self, name: str) -> ModelConfigRecord | None:
        ...

    @abstractmethod
    async def update(
        self,
        name: str,
        *,
        unit_cost: Decimal | None = None,
        enabled: bool | None = None,
        extra: Mapping[str, Any] | None = None,
    ) -> ModelConfigRecord:
        """部分更新（仅改传入字段）。name 不存在 → NotFoundError（边界映射 404）。"""
        ...

    @abstractmethod
    async def seed_defaults(self, defaults: Sequence[ModelConfigRecord]) -> None:
        """播种默认配置：仅插入缺失的 name，已存在的不覆盖（保护管理员改价）。"""
        ...
