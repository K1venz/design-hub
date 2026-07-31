from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal

from design_hub.domain.enums import ModelType, ProviderType


@dataclass(frozen=True)
class ModelConfigRecord:
    name: str
    display_name: str
    model_type: ModelType
    provider_type: ProviderType
    base_url: str
    model: str
    credentials_ciphertext: dict[str, str | list[str]]
    unit_cost: Decimal
    enabled: bool
    revision: int
    verified_at: datetime | None
    verified_fingerprint: str | None
    extra: dict[str, object]


class ModelConfigRepository(ABC):
    @abstractmethod
    async def list_all(self) -> list[ModelConfigRecord]: ...

    @abstractmethod
    async def get(self, name: str) -> ModelConfigRecord | None: ...

    @abstractmethod
    async def get_default(self, model_type: ModelType) -> str | None: ...

    @abstractmethod
    async def create(self, *, actor_id: int, record: ModelConfigRecord) -> ModelConfigRecord: ...

    @abstractmethod
    async def update(self, *, actor_id: int, record: ModelConfigRecord) -> ModelConfigRecord: ...

    @abstractmethod
    async def delete(self, *, actor_id: int, name: str) -> None: ...

    @abstractmethod
    async def set_default(self, *, actor_id: int, name: str) -> ModelConfigRecord: ...
