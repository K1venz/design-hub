from dataclasses import dataclass

from design_hub.domain.models import GeneratedImage
from design_hub.ports.model_provider import (
    AbstractModelProvider,
    ProviderError,
    ProviderTimeout,
    ReferenceMode,
)
from design_hub.ports.provider_execution import (
    ImmediateResult,
    ProviderRequest,
    RecoverableTaskProvider,
    SubmissionUncertain,
    SubmittedTask,
    UnsupportedProviderResume,
)


@dataclass(frozen=True)
class ProviderExecutionAdapter:
    provider: AbstractModelProvider

    @property
    def reference_mode(self) -> ReferenceMode:
        return self.provider.reference_mode

    async def submit(
        self, request: ProviderRequest, *, operation_id: str
    ) -> SubmittedTask | ImmediateResult:
        if isinstance(self.provider, RecoverableTaskProvider):
            task_id = await self.provider.submit_task(
                request, operation_id=operation_id
            )
            return SubmittedTask(provider_task_id=task_id)
        try:
            images = await self.provider.generate(
                prompt=request.prompt,
                negative_prompt="",
                reference_images=list(request.reference_images),
                size=request.size,
                n=1,
                seed=request.seed,
                quality=request.quality,
            )
        except ProviderTimeout as exc:
            raise SubmissionUncertain(
                "non-resumable provider submission outcome is unknown"
            ) from exc
        if len(images) != 1:
            raise ProviderError(
                f"single image provider returned {len(images)} images"
            )
        return ImmediateResult(image=images[0])

    async def resume(
        self, provider_task_id: str, request: ProviderRequest
    ) -> GeneratedImage:
        if not isinstance(self.provider, RecoverableTaskProvider):
            raise UnsupportedProviderResume(
                "provider does not expose a resumable task lifecycle"
            )
        return await self.provider.resume_task(provider_task_id, request)
