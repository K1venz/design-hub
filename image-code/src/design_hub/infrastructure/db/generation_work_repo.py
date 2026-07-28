from datetime import UTC, datetime
from decimal import Decimal
from uuid import uuid4

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from design_hub.domain.errors import DataInvariantError
from design_hub.domain.tasking import GenerationItemStatus, TaskMessage
from design_hub.infrastructure.db.models import (
    AppUser,
    CostLedgerEntry,
    GenerationItemRow,
    ListingJobInputRow,
    ListingJobRow,
    OutboxEventRow,
)
from design_hub.ports.generation_work import (
    IdempotencyConflict,
    JobSubmission,
    OutboxRecord,
    SubmitResult,
)


class SqlAlchemyGenerationWorkRepository:
    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._session_factory = session_factory

    async def submit(self, submission: JobSubmission) -> SubmitResult:
        if not submission.items:
            raise ValueError("generation submission must contain at least one item")
        async with self._session_factory() as session:
            async with session.begin():
                existing = await session.scalar(
                    select(ListingJobRow).where(
                        ListingJobRow.user_id == submission.job.user_id,
                        ListingJobRow.idempotency_key == submission.idempotency_key,
                    )
                )
                if existing is not None:
                    if existing.request_fingerprint != submission.request_fingerprint:
                        raise IdempotencyConflict(
                            "idempotency key was already used for a different request"
                        )
                    return SubmitResult(job_id=existing.id, replayed=True)

                await self._lock_user(session, submission.job.user_id)
                active_count = await session.scalar(
                    select(func.count())
                    .select_from(ListingJobRow)
                    .where(
                        ListingJobRow.user_id == submission.job.user_id,
                        ListingJobRow.status == "生成中",
                    )
                )
                if active_count:
                    raise ValueError("user already has an active generation job")

                session.add(self._job_row(submission))
                for index, item in enumerate(submission.items):
                    session.add(
                        GenerationItemRow(
                            id=item.item_id,
                            job_id=submission.job.job_id,
                            sequence=item.sequence,
                            image_type=item.image_type,
                            render_tier=item.render_tier.value,
                            operation_type=item.operation_type.value,
                            final_prompt=item.final_prompt,
                            model=item.model.value,
                            ratio=item.ratio,
                            size=f"{item.size[0]}x{item.size[1]}",
                            quality=item.quality,
                            seed=item.seed,
                            reference_snapshot=[
                                {
                                    "source": ref.source.value,
                                    "object_key": ref.object_key,
                                    "role": ref.role,
                                    "order": ref.order,
                                }
                                for ref in item.references
                            ],
                            reserved_cost=item.reserved_cost,
                            status=(
                                GenerationItemStatus.QUEUED.value
                                if index == 0
                                else GenerationItemStatus.WAITING.value
                            ),
                            operation_id=item.operation_id,
                            attempt_count=0,
                        )
                    )
                    session.add(
                        CostLedgerEntry(
                            operation_id=f"reserve:{item.operation_id}",
                            user_id=submission.job.user_id,
                            amount=item.reserved_cost,
                        )
                    )
                session.add(self._first_outbox(submission))
            return SubmitResult(job_id=submission.job.job_id, replayed=False)

    async def fetch_outbox_batch(
        self, *, limit: int
    ) -> tuple[OutboxRecord, ...]:
        if limit <= 0:
            raise ValueError("outbox batch limit must be positive")
        async with self._session_factory() as session:
            rows = (
                await session.execute(
                    select(OutboxEventRow)
                    .where(OutboxEventRow.published_at.is_(None))
                    .order_by(OutboxEventRow.created_at, OutboxEventRow.id)
                    .limit(limit)
                )
            ).scalars()
            return tuple(
                OutboxRecord(
                    event_id=row.id,
                    payload=row.payload,
                    created_at=row.created_at,
                    publish_attempts=row.publish_attempts,
                )
                for row in rows
            )

    async def mark_outbox_published(
        self, event_id: str, redis_id: str
    ) -> None:
        async with self._session_factory() as session:
            row = await session.get(OutboxEventRow, event_id)
            if row is None:
                raise DataInvariantError(f"outbox event {event_id} does not exist")
            if row.published_at is not None:
                if row.redis_id != redis_id:
                    raise DataInvariantError(
                        f"outbox event {event_id} already has Redis id {row.redis_id}"
                    )
                return
            row.redis_id = redis_id
            row.published_at = datetime.now(UTC)
            row.last_error = None
            await session.commit()

    async def record_outbox_failure(self, event_id: str, error: str) -> None:
        async with self._session_factory() as session:
            row = await session.get(OutboxEventRow, event_id)
            if row is None:
                raise DataInvariantError(f"outbox event {event_id} does not exist")
            row.publish_attempts += 1
            row.last_error = error[:1000]
            await session.commit()

    @staticmethod
    async def _lock_user(session: AsyncSession, user_id: str) -> None:
        try:
            numeric_user_id = int(user_id)
        except ValueError as exc:
            raise ValueError("authenticated user_id must be numeric") from exc
        user = await session.scalar(
            select(AppUser).where(AppUser.id == numeric_user_id).with_for_update()
        )
        if user is None:
            raise ValueError(f"authenticated user {user_id} does not exist")

    @staticmethod
    def _job_row(submission: JobSubmission) -> ListingJobRow:
        job = submission.job
        row = ListingJobRow(
            id=job.job_id,
            user_id=job.user_id,
            idempotency_key=submission.idempotency_key,
            request_fingerprint=submission.request_fingerprint,
            prompt=job.prompt,
            modifiers=dict(job.modifiers),
            platform=job.modifiers.get("platform"),
            category=job.category,
            ratio=job.ratio,
            size=job.size,
            n=job.n,
            status="生成中",
            total_cost=Decimal("0"),
            error=None,
            clone_mode=job.clone_mode,
            parent_job_id=job.parent_job_id,
            source_image_key=job.source_image_key,
            edit_mode=job.edit_mode,
            completed_at=None,
        )
        roles = job.input_roles or (None,) * len(job.upload_keys)
        row.inputs = [
            ListingJobInputRow(upload_key=key, role=role, ord=index)
            for index, (key, role) in enumerate(
                zip(job.upload_keys, roles, strict=True)
            )
        ]
        return row

    @staticmethod
    def _first_outbox(submission: JobSubmission) -> OutboxEventRow:
        first = submission.items[0]
        now = datetime.now(UTC)
        message = TaskMessage(
            schema_version=1,
            message_id=uuid4().hex,
            trace_id=submission.trace_id,
            request_id=submission.request_id,
            job_id=submission.job.job_id,
            item_id=first.item_id,
            operation_id=first.operation_id,
            operation_type=first.operation_type,
            user_id=submission.job.user_id,
            created_at=now,
        )
        return OutboxEventRow(
            id=uuid4().hex,
            aggregate_type="generation_item",
            aggregate_id=first.item_id,
            event_type="generation_item.queued",
            payload=message.to_redis_fields(),
            publish_attempts=0,
        )
