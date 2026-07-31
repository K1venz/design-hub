from datetime import UTC, datetime
from decimal import Decimal
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from design_hub.domain.admin import ModelCallStatus
from design_hub.domain.errors import DataInvariantError
from design_hub.infrastructure.db.models import ModelCallRow
from design_hub.ports.model_calls import ModelCallContext, ModelCallRecorder, ModelUsage

_MAX_ERROR_DETAIL = 500
_MAX_ERROR_CODE = 64


class SqlAlchemyModelCallRecorder(ModelCallRecorder):
    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession],
    ) -> None:
        self._session_factory = session_factory

    async def start(
        self,
        *,
        context: ModelCallContext,
        provider: str,
        model: str,
        attempt_no: int,
    ) -> str:
        if attempt_no < 1:
            raise ValueError("attempt_no must be positive")
        call_id = uuid4().hex
        async with self._session_factory() as session:
            session.add(
                ModelCallRow(
                    id=call_id,
                    user_id=context.user_id,
                    provider=provider,
                    model=model,
                    modality=context.modality.value,
                    operation_type=context.operation.value,
                    job_id=context.job_id,
                    generation_item_id=context.generation_item_id,
                    chat_session_id=context.chat_session_id,
                    attempt_no=attempt_no,
                    status=ModelCallStatus.STARTED.value,
                )
            )
            await session.commit()
        return call_id

    async def succeed(
        self,
        call_id: str,
        *,
        usage: ModelUsage,
        provider_request_id: str | None,
        platform_cost: Decimal | None,
        diagnostic_code: str | None = None,
    ) -> None:
        if diagnostic_code is not None:
            self._validate_code(diagnostic_code)
        async with self._session_factory() as session:
            async with session.begin():
                row = await self._started_row(session, call_id)
                row.status = ModelCallStatus.SUCCEEDED.value
                row.provider_request_id = provider_request_id
                row.input_tokens = usage.input_tokens
                row.output_tokens = usage.output_tokens
                row.total_tokens = usage.total_tokens
                row.input_text_tokens = usage.input_text_tokens
                row.input_image_tokens = usage.input_image_tokens
                row.output_image_tokens = usage.output_image_tokens
                row.error_code = diagnostic_code
                row.error_detail = None
                row.platform_cost = platform_cost
                self._complete(row)

    async def fail(self, call_id: str, *, code: str, detail: str) -> None:
        self._validate_code(code)
        async with self._session_factory() as session:
            async with session.begin():
                row = await self._started_row(session, call_id)
                row.status = ModelCallStatus.FAILED.value
                row.error_code = code
                row.error_detail = detail[:_MAX_ERROR_DETAIL]
                self._complete(row)

    async def uncertain(self, call_id: str, *, detail: str) -> None:
        async with self._session_factory() as session:
            async with session.begin():
                row = await self._started_row(session, call_id)
                row.status = ModelCallStatus.UNCERTAIN.value
                row.error_code = "submission_uncertain"
                row.error_detail = detail[:_MAX_ERROR_DETAIL]
                self._complete(row)

    async def interrupt(self, call_id: str) -> None:
        async with self._session_factory() as session:
            async with session.begin():
                row = await self._started_row(session, call_id)
                row.status = ModelCallStatus.INTERRUPTED.value
                row.error_code = "cancelled"
                self._complete(row)

    @staticmethod
    async def _started_row(
        session: AsyncSession,
        call_id: str,
    ) -> ModelCallRow:
        row = (
            await session.execute(
                select(ModelCallRow)
                .where(ModelCallRow.id == call_id)
                .with_for_update()
            )
        ).scalar_one_or_none()
        if row is None:
            raise DataInvariantError(f"model call {call_id} not found")
        if row.status != ModelCallStatus.STARTED.value:
            raise DataInvariantError(f"model call {call_id} already finalized")
        return row

    @staticmethod
    def _complete(row: ModelCallRow) -> None:
        completed_at = datetime.now(UTC)
        started_at = row.started_at
        if started_at.tzinfo is None:
            started_at = started_at.replace(tzinfo=UTC)
        row.completed_at = completed_at
        row.latency_ms = max(
            int((completed_at - started_at).total_seconds() * 1000),
            0,
        )

    @staticmethod
    def _validate_code(code: str) -> None:
        if not code or len(code) > _MAX_ERROR_CODE:
            raise ValueError("model call diagnostic code must be 1..64 characters")
