from dataclasses import dataclass
from typing import Protocol, runtime_checkable

from design_hub.domain.models import GeneratedImage, ReferenceImage
from design_hub.ports.model_calls import ModelCallContext
from design_hub.ports.model_provider import ReferenceMode


class SubmissionUncertain(RuntimeError):
    pass


class UnsupportedProviderResume(RuntimeError):
    pass


@dataclass(frozen=True)
class ProviderRequest:
    context: ModelCallContext
    prompt: str
    reference_images: tuple[ReferenceImage, ...]
    size: tuple[int, int]
    seed: int
    quality: str | None


@dataclass(frozen=True)
class SubmittedTask:
    provider_task_id: str


@dataclass(frozen=True)
class ImmediateResult:
    image: GeneratedImage


@runtime_checkable
class RecoverableTaskProvider(Protocol):
    async def submit_task(
        self, request: ProviderRequest, *, operation_id: str
    ) -> str: ...

    async def resume_task(
        self, provider_task_id: str, request: ProviderRequest
    ) -> GeneratedImage: ...


class ProviderExecutor(Protocol):
    @property
    def reference_mode(self) -> ReferenceMode: ...

    async def submit(
        self, request: ProviderRequest, *, operation_id: str
    ) -> SubmittedTask | ImmediateResult: ...

    async def resume(
        self, provider_task_id: str, request: ProviderRequest
    ) -> GeneratedImage: ...
