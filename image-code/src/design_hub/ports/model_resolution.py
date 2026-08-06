from typing import Protocol

from design_hub.domain.enums import ModelType
from design_hub.domain.tasking import RenderTier
from design_hub.ports.provider_execution import ProviderExecutor
from design_hub.ports.text_llm import TextLLMPort


class ModelUnavailableError(RuntimeError):
    """A configured runtime model cannot be used for this operation."""


class ImageExecutorResolver(Protocol):
    async def resolve(
        self, model_id: str, render_tier: RenderTier
    ) -> ProviderExecutor: ...


class TextLLMResolver(Protocol):
    async def resolve(
        self,
        model_id: str,
        model_type: ModelType,
    ) -> TextLLMPort: ...

    async def resolve_default(
        self,
        model_type: ModelType,
    ) -> TextLLMPort: ...
