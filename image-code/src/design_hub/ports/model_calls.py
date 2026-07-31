from dataclasses import dataclass
from decimal import Decimal
from typing import Protocol

from design_hub.domain.admin import ModelModality, ModelOperation


@dataclass(frozen=True)
class ModelCallContext:
    user_id: str
    operation: ModelOperation
    job_id: str | None = None
    generation_item_id: str | None = None
    chat_session_id: str | None = None

    @property
    def modality(self) -> ModelModality:
        if self.operation in {
            ModelOperation.CHAT_COMPLETION,
            ModelOperation.REVERSE_PROMPT,
        }:
            return ModelModality.CHAT
        return ModelModality.IMAGE


@dataclass(frozen=True)
class ModelUsage:
    input_tokens: int | None = None
    output_tokens: int | None = None
    total_tokens: int | None = None
    input_text_tokens: int | None = None
    input_image_tokens: int | None = None
    output_image_tokens: int | None = None


class ModelCallRecorder(Protocol):
    async def start(
        self,
        *,
        context: ModelCallContext,
        provider: str,
        model: str,
        attempt_no: int,
    ) -> str: ...

    async def succeed(
        self,
        call_id: str,
        *,
        usage: ModelUsage,
        provider_request_id: str | None,
        platform_cost: Decimal | None,
        diagnostic_code: str | None = None,
    ) -> None: ...

    async def fail(self, call_id: str, *, code: str, detail: str) -> None: ...

    async def uncertain(self, call_id: str, *, detail: str) -> None: ...

    async def interrupt(self, call_id: str) -> None: ...
