import asyncio
import base64
from decimal import Decimal
from importlib import import_module

import httpx
import pytest
from model_call_fakes import RecordingModelCallRecorder
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from design_hub.domain.admin import ModelCallStatus, ModelOperation
from design_hub.domain.errors import DataInvariantError
from design_hub.domain.models import ReferenceImage
from design_hub.infrastructure.db.base import Base
from design_hub.infrastructure.db.models import ModelCallRow
from design_hub.infrastructure.providers.api_key_pool import ApiKeyPool
from design_hub.infrastructure.providers.openai_compat import (
    OpenAICompatImageProvider,
)
from design_hub.ports.image_store import ImageStore, StoredImage
from design_hub.ports.model_calls import ModelCallContext


async def _database() -> tuple[async_sessionmaker[AsyncSession], AsyncEngine]:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    return async_sessionmaker(engine, expire_on_commit=False), engine


def _recorder_types() -> tuple[type, type, type]:
    try:
        ports = import_module("design_hub.ports.model_calls")
        repository = import_module(
            "design_hub.infrastructure.db.model_call_repo"
        )
    except ModuleNotFoundError:
        pytest.fail("model call recorder is missing")
    return (
        ports.ModelCallContext,
        ports.ModelUsage,
        repository.SqlAlchemyModelCallRecorder,
    )


def test_recorder_persists_start_before_successful_finalization() -> None:
    async def run() -> None:
        context_type, usage_type, recorder_type = _recorder_types()
        sessions, engine = await _database()
        try:
            recorder = recorder_type(sessions)
            call_id = await recorder.start(
                context=context_type(
                    user_id="7",
                    operation=ModelOperation.IMAGE_EDIT,
                    job_id="job-1",
                    generation_item_id="item-1",
                ),
                provider="openai_compat_image",
                model="gpt-image-2",
                attempt_no=2,
            )
            async with sessions() as session:
                started = await session.get(ModelCallRow, call_id)
                assert started is not None
                assert started.status == ModelCallStatus.STARTED.value
                assert started.attempt_no == 2
                assert started.completed_at is None

            await recorder.succeed(
                call_id,
                usage=usage_type(
                    input_tokens=1564,
                    output_tokens=1105,
                    total_tokens=2669,
                    input_text_tokens=34,
                    input_image_tokens=1530,
                    output_image_tokens=1105,
                ),
                provider_request_id="request-1",
                platform_cost=Decimal("0.05"),
            )

            async with sessions() as session:
                completed = await session.get(ModelCallRow, call_id)
                assert completed is not None
                assert completed.status == ModelCallStatus.SUCCEEDED.value
                assert completed.input_tokens == 1564
                assert completed.output_image_tokens == 1105
                assert completed.provider_request_id == "request-1"
                assert completed.platform_cost == Decimal("0.05")
                assert completed.completed_at is not None
                assert completed.latency_ms is not None
        finally:
            await engine.dispose()

    asyncio.run(run())


def test_recorder_rejects_a_second_finalization() -> None:
    async def run() -> None:
        context_type, usage_type, recorder_type = _recorder_types()
        sessions, engine = await _database()
        try:
            recorder = recorder_type(sessions)
            call_id = await recorder.start(
                context=context_type(
                    user_id="7",
                    operation=ModelOperation.IMAGE_GENERATION,
                ),
                provider="openai_compat_image",
                model="gpt-image-2",
                attempt_no=1,
            )
            await recorder.fail(
                call_id,
                code="provider_timeout",
                detail="timeout",
            )

            with pytest.raises(DataInvariantError, match="already finalized"):
                await recorder.succeed(
                    call_id,
                    usage=usage_type(),
                    provider_request_id=None,
                    platform_cost=None,
                )
        finally:
            await engine.dispose()

    asyncio.run(run())


def test_recorder_caps_external_error_detail() -> None:
    async def run() -> None:
        context_type, _usage_type, recorder_type = _recorder_types()
        sessions, engine = await _database()
        try:
            recorder = recorder_type(sessions)
            call_id = await recorder.start(
                context=context_type(
                    user_id="7",
                    operation=ModelOperation.IMAGE_GENERATION,
                ),
                provider="openai_compat_image",
                model="gpt-image-2",
                attempt_no=1,
            )
            await recorder.fail(
                call_id,
                code="provider_timeout",
                detail="x" * 900,
            )

            async with sessions() as session:
                row = await session.get(ModelCallRow, call_id)
                assert row is not None
                assert row.status == ModelCallStatus.FAILED.value
                assert row.error_detail == "x" * 500
        finally:
            await engine.dispose()

    asyncio.run(run())


class _ImageStore(ImageStore):
    async def save(self, data: bytes, *, suffix: str = ".png") -> StoredImage:
        return StoredImage(key=f"stored{suffix}", url=f"stored://image{suffix}")

    async def load(self, image_key: str) -> bytes:
        raise NotImplementedError


class _SequencedClient:
    def __init__(self, outcomes: list[httpx.Response]) -> None:
        self.outcomes = list(outcomes)
        self.posts = 0

    async def post(self, *args: object, **kwargs: object) -> httpx.Response:
        self.posts += 1
        return self.outcomes.pop(0)


def _image_response(status: int, *, usage: bool = False) -> httpx.Response:
    if status != 200:
        return httpx.Response(status, text="busy")
    body: dict[str, object] = {
        "data": [
            {
                "b64_json": base64.b64encode(b"PNG").decode(),
            }
        ]
    }
    if usage:
        body["usage"] = {
            "input_tokens": 1564,
            "output_tokens": 1105,
            "total_tokens": 2669,
            "input_tokens_details": {
                "text_tokens": 34,
                "image_tokens": 1530,
            },
            "output_tokens_details": {
                "text_tokens": 0,
                "image_tokens": 1105,
            },
        }
    return httpx.Response(200, json=body, headers={"x-request-id": "request-2"})


def test_each_gpt_image_retry_is_recorded_with_upstream_usage() -> None:
    async def run() -> None:
        recorder = RecordingModelCallRecorder()
        client = _SequencedClient(
            [_image_response(429), _image_response(200, usage=True)]
        )
        provider = OpenAICompatImageProvider(
            name="gpt-image-2",
            unit_cost=Decimal("0.05"),
            base_url="https://example.invalid",
            key_pool=ApiKeyPool(("key-a", "key-b")),
            model="gpt-image-2",
            image_store=_ImageStore(),
            recorder=recorder,
            client=client,  # type: ignore[arg-type]
            max_retries=1,
            retry_backoff=0,
            retry_max_sleep=0,
        )

        images = await provider.generate(
            context=ModelCallContext(
                user_id="7",
                operation=ModelOperation.IMAGE_EDIT,
                job_id="job-1",
                generation_item_id="item-1",
            ),
            prompt="edit",
            negative_prompt="",
            reference_images=[ReferenceImage(data=b"product")],
            size=(1024, 1024),
            n=1,
        )

        assert len(images) == 1
        assert [call.attempt_no for call in recorder.started] == [1, 2]
        assert recorder.failed[0].call_id == "call-1"
        assert recorder.succeeded[0].call_id == "call-2"
        assert recorder.succeeded[0].provider_request_id == "request-2"
        assert recorder.succeeded[0].usage.total_tokens == 2669
        assert recorder.succeeded[0].usage.input_image_tokens == 1530

    asyncio.run(run())


def test_recorder_start_failure_prevents_upstream_image_request() -> None:
    async def run() -> None:
        recorder = RecordingModelCallRecorder(start_error=RuntimeError("database down"))
        client = _SequencedClient([_image_response(200)])
        provider = OpenAICompatImageProvider(
            name="gpt-image-2",
            unit_cost=Decimal("0.05"),
            base_url="https://example.invalid",
            key_pool=ApiKeyPool(("key-a",)),
            model="gpt-image-2",
            image_store=_ImageStore(),
            recorder=recorder,
            client=client,  # type: ignore[arg-type]
        )

        with pytest.raises(RuntimeError, match="database down"):
            await provider.generate(
                context=ModelCallContext(
                    user_id="7",
                    operation=ModelOperation.IMAGE_GENERATION,
                ),
                prompt="generate",
                negative_prompt="",
                reference_images=[],
                size=(1024, 1024),
                n=1,
            )

        assert client.posts == 0

    asyncio.run(run())
