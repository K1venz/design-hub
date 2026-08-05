import asyncio
from decimal import Decimal

import pytest

from design_hub.domain.admin import ModelOperation
from design_hub.domain.image_capabilities import ImageOutputSpec
from design_hub.domain.models import GeneratedImage, ReferenceImage
from design_hub.domain.tasking import RenderTier
from design_hub.infrastructure.providers.execution import ProviderExecutionAdapter
from design_hub.ports.model_calls import ModelCallContext
from design_hub.ports.model_provider import (
    AbstractModelProvider,
    ProviderTimeout,
)
from design_hub.ports.provider_execution import (
    ImmediateResult,
    ProviderRequest,
    SubmissionUncertain,
    SubmittedTask,
    UnsupportedProviderResume,
)


def _image() -> GeneratedImage:
    return GeneratedImage(
        image_key="result.png",
        url="mock://result.png",
        seed=0,
        latency_ms=10,
        cost=Decimal("0.05"),
    )


def _request() -> ProviderRequest:
    return ProviderRequest(
        context=ModelCallContext(
            user_id="7",
            operation=ModelOperation.IMAGE_EDIT,
        ),
        prompt="faithful product",
        reference_images=(ReferenceImage(data=b"product"),),
        output=ImageOutputSpec(
            ratio="1:1",
            render_tier=RenderTier.STANDARD,
            size=(1024, 1024),
        ),
        seed=0,
        quality=None,
    )


class _ImmediateProvider(AbstractModelProvider):
    name = "gpt-image-2"
    unit_cost = Decimal("0.05")

    def __init__(self, *, error: Exception | None = None) -> None:
        self.error = error
        self.calls = 0

    async def generate(
        self,
        *,
        context: ModelCallContext,
        prompt: str,
        negative_prompt: str,
        reference_images: list[ReferenceImage],
        output: ImageOutputSpec,
        n: int,
        seed: int | None = None,
        quality: str | None = None,
    ) -> list[GeneratedImage]:
        del context
        self.output = output
        self.calls += 1
        if self.error is not None:
            raise self.error
        return [_image()]


class _RecoverableProvider(_ImmediateProvider):
    def __init__(self) -> None:
        super().__init__()
        self.submissions: list[tuple[ProviderRequest, str]] = []
        self.resumes: list[tuple[str, ProviderRequest]] = []

    async def submit_task(
        self, request: ProviderRequest, *, operation_id: str
    ) -> str:
        self.submissions.append((request, operation_id))
        return "provider-task-1"

    async def resume_task(
        self, provider_task_id: str, request: ProviderRequest
    ) -> GeneratedImage:
        self.resumes.append((provider_task_id, request))
        return _image()


def test_recoverable_provider_returns_task_id_then_resumes_without_resubmit() -> None:
    async def run() -> None:
        provider = _RecoverableProvider()
        executor = ProviderExecutionAdapter(provider)

        submitted = await executor.submit(_request(), operation_id="operation-1")
        assert submitted == SubmittedTask(provider_task_id="provider-task-1")
        image = await executor.resume("provider-task-1", _request())

        assert image == _image()
        assert provider.submissions == [(_request(), "operation-1")]
        assert provider.resumes == [("provider-task-1", _request())]
        assert provider.calls == 0

    asyncio.run(run())


def test_immediate_provider_returns_image_and_cannot_resume() -> None:
    async def run() -> None:
        provider = _ImmediateProvider()
        executor = ProviderExecutionAdapter(provider)

        result = await executor.submit(_request(), operation_id="operation-1")

        assert result == ImmediateResult(image=_image())
        assert provider.calls == 1
        assert provider.output == _request().output
        with pytest.raises(UnsupportedProviderResume):
            await executor.resume("provider-task-1", _request())

    asyncio.run(run())


def test_timeout_from_non_resumable_submission_is_uncertain() -> None:
    async def run() -> None:
        provider = _ImmediateProvider(error=ProviderTimeout("timeout after submit"))
        executor = ProviderExecutionAdapter(provider)

        with pytest.raises(SubmissionUncertain):
            await executor.submit(_request(), operation_id="operation-1")

        assert provider.calls == 1

    asyncio.run(run())
