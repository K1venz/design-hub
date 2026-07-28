from datetime import UTC, datetime, timedelta
from decimal import Decimal
from uuid import uuid4

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from design_hub.application.cost.budget import BudgetPolicy
from design_hub.domain.enums import ModelName, TaskEventType
from design_hub.domain.errors import DataInvariantError
from design_hub.domain.models import BudgetSnapshot, GeneratedImage
from design_hub.domain.tasking import (
    GenerationItemSpec,
    GenerationItemStatus,
    OperationType,
    ReferenceSnapshot,
    ReferenceSource,
    RenderTier,
    TaskMessage,
    is_terminal,
)
from design_hub.infrastructure.db.models import (
    AppUser,
    CostLedgerEntry,
    GenerationItemRow,
    ListingImageRow,
    ListingJobInputRow,
    ListingJobRow,
    OutboxEventRow,
)
from design_hub.infrastructure.ledger.sqlalchemy_ledger import month_start_utc
from design_hub.ports.generation_work import (
    ConcurrentTaskMutation,
    GenerationWorkItem,
    IdempotencyConflict,
    JobSubmission,
    OutboxRecord,
    OutboxStats,
    SubmitResult,
)

_ACTIVE_STATUSES = (
    GenerationItemStatus.CLAIMED.value,
    GenerationItemStatus.SUBMITTING.value,
    GenerationItemStatus.SUBMITTED.value,
    GenerationItemStatus.PROCESSING.value,
    GenerationItemStatus.STORING.value,
)
_OWNED_FAILURE_STATUSES = (
    GenerationItemStatus.CLAIMED.value,
    GenerationItemStatus.SUBMITTING.value,
    GenerationItemStatus.SUBMITTED.value,
    GenerationItemStatus.PROCESSING.value,
    GenerationItemStatus.STORING.value,
)
_SAFE_ERROR_LIMIT = 500


class SqlAlchemyGenerationWorkRepository:
    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession],
        *,
        user_quota: Decimal = Decimal("200"),
        company_budget: Decimal = Decimal("800"),
        budget_policy: BudgetPolicy | None = None,
    ) -> None:
        self._session_factory = session_factory
        self._user_quota = user_quota
        self._company_budget = company_budget
        self._budget_policy = budget_policy or BudgetPolicy()

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
                await self._require_budget(session, submission)
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

                job_row = self._job_row(submission)
                for index, item in enumerate(submission.items):
                    job_row.generation_items.append(
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
                session.add(job_row)
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
                    aggregate_type=row.aggregate_type,
                    event_type=row.event_type,
                )
                for row in rows
            )

    async def outbox_stats(self) -> OutboxStats:
        async with self._session_factory() as session:
            pending, oldest = (
                await session.execute(
                    select(
                        func.count(OutboxEventRow.id),
                        func.min(OutboxEventRow.created_at),
                    ).where(OutboxEventRow.published_at.is_(None))
                )
            ).one()
            return OutboxStats(
                pending=int(pending),
                oldest_created_at=oldest,
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

    async def load_item(self, item_id: str) -> GenerationWorkItem:
        async with self._session_factory() as session:
            result = (
                await session.execute(
                    select(GenerationItemRow, ListingJobRow.user_id)
                    .join(ListingJobRow, ListingJobRow.id == GenerationItemRow.job_id)
                    .where(GenerationItemRow.id == item_id)
                )
            ).one_or_none()
            if result is None:
                raise DataInvariantError(f"generation item {item_id} does not exist")
            row, user_id = result
            return self._to_work_item(row, user_id)

    async def claim(
        self, item_id: str, worker_id: str, lease_seconds: int
    ) -> None:
        if lease_seconds <= 0:
            raise ValueError("lease_seconds must be positive")
        now = datetime.now(UTC)
        async with self._session_factory() as session:
            async with session.begin():
                row = await session.get(GenerationItemRow, item_id)
                if row is None:
                    raise ConcurrentTaskMutation(
                        f"generation item {item_id} does not exist"
                    )
                status = GenerationItemStatus(row.status)
                reclaimable = {
                    GenerationItemStatus.CLAIMED,
                    GenerationItemStatus.SUBMITTING,
                    GenerationItemStatus.SUBMITTED,
                    GenerationItemStatus.PROCESSING,
                    GenerationItemStatus.STORING,
                }
                if status is GenerationItemStatus.QUEUED:
                    await self._require_user_capacity(session, row.job_id)
                    target_status = GenerationItemStatus.CLAIMED.value
                elif status in reclaimable and self._lease_is_expired(
                    row.lease_expires_at, now
                ):
                    target_status = row.status
                else:
                    raise ConcurrentTaskMutation(
                        f"generation item {item_id} cannot be claimed from {status}"
                    )
                result = await session.execute(
                    update(GenerationItemRow)
                    .where(
                        GenerationItemRow.id == item_id,
                        GenerationItemRow.status == row.status,
                        GenerationItemRow.worker_id == row.worker_id,
                    )
                    .values(
                        status=target_status,
                        worker_id=worker_id,
                        lease_expires_at=now + timedelta(seconds=lease_seconds),
                        heartbeat_at=now,
                        attempt_count=GenerationItemRow.attempt_count + 1,
                    )
                )
                self._require_one(
                    getattr(result, "rowcount", None), item_id, "claim"
                )
                if status is GenerationItemStatus.QUEUED:
                    self._add_job_event(
                        session,
                        job_id=row.job_id,
                        event_type=TaskEventType.TASK_STARTED,
                        data={
                            "item_id": row.id,
                            "status": GenerationItemStatus.CLAIMED.value,
                        },
                    )

    async def mark_submitting(
        self, item_id: str, worker_id: str
    ) -> None:
        async with self._session_factory() as session:
            async with session.begin():
                await self._owned_transition(
                    session,
                    item_id,
                    worker_id,
                    (GenerationItemStatus.CLAIMED,),
                    GenerationItemStatus.SUBMITTING,
                )

    async def mark_submitted(
        self, item_id: str, worker_id: str, provider_task_id: str
    ) -> None:
        if not provider_task_id:
            raise ValueError("provider_task_id must not be empty")
        async with self._session_factory() as session:
            async with session.begin():
                row = await self._owned_transition(
                    session,
                    item_id,
                    worker_id,
                    (GenerationItemStatus.SUBMITTING,),
                    GenerationItemStatus.SUBMITTED,
                    provider_task_id=provider_task_id,
                )
                await session.flush()
                await self._release_next_item(session, row.job_id)

    async def mark_processing(
        self, item_id: str, worker_id: str
    ) -> None:
        async with self._session_factory() as session:
            async with session.begin():
                await self._owned_transition(
                    session,
                    item_id,
                    worker_id,
                    (GenerationItemStatus.SUBMITTED,),
                    GenerationItemStatus.PROCESSING,
                )

    async def mark_storing(
        self, item_id: str, worker_id: str
    ) -> None:
        async with self._session_factory() as session:
            async with session.begin():
                await self._owned_transition(
                    session,
                    item_id,
                    worker_id,
                    (
                        GenerationItemStatus.SUBMITTING,
                        GenerationItemStatus.PROCESSING,
                    ),
                    GenerationItemStatus.STORING,
                )

    async def complete_item(
        self,
        item_id: str,
        worker_id: str,
        image: GeneratedImage,
    ) -> None:
        async with self._session_factory() as session:
            async with session.begin():
                row = await self._owned_transition(
                    session,
                    item_id,
                    worker_id,
                    (GenerationItemStatus.STORING,),
                    GenerationItemStatus.GENERATED,
                    worker_id=None,
                    lease_expires_at=None,
                    heartbeat_at=None,
                    error_code=None,
                    error_detail=None,
                )
                job = await session.get(ListingJobRow, row.job_id)
                if job is None:
                    raise DataInvariantError(
                        f"listing job {row.job_id} does not exist"
                    )
                session.add(
                    ListingImageRow(
                        job_id=row.job_id,
                        image_key=image.image_key,
                        image_type=image.image_type or row.image_type,
                        seed=image.seed,
                        cost=image.cost,
                        status="成功",
                    )
                )
                await self._append_ledger(
                    session,
                    operation_id=f"reconcile:{row.id}",
                    user_id=job.user_id,
                    amount=image.cost - row.reserved_cost,
                )
                self._add_job_event(
                    session,
                    job_id=row.job_id,
                    event_type=TaskEventType.IMAGE_GENERATED,
                    data={
                        "item_id": row.id,
                        "image_key": image.image_key,
                        "image_type": image.image_type or row.image_type,
                        "seed": image.seed,
                        "cost": str(image.cost),
                    },
                )
                await session.flush()
                await self._release_next_item(session, row.job_id)
                job_status = await self._aggregate_job(session, row.job_id)
                if job_status is not None:
                    self._add_terminal_job_event(
                        session, row.job_id, job_status
                    )

    async def fail_item(
        self,
        item_id: str,
        worker_id: str,
        error_code: str,
        error_detail: str,
    ) -> None:
        safe_code = error_code[:64]
        safe_detail = error_detail[:_SAFE_ERROR_LIMIT]
        async with self._session_factory() as session:
            async with session.begin():
                row = await self._owned_transition(
                    session,
                    item_id,
                    worker_id,
                    tuple(
                        GenerationItemStatus(status)
                        for status in _OWNED_FAILURE_STATUSES
                    ),
                    GenerationItemStatus.FAILED,
                    worker_id=None,
                    lease_expires_at=None,
                    heartbeat_at=None,
                    error_code=safe_code,
                    error_detail=safe_detail,
                )
                job = await session.get(ListingJobRow, row.job_id)
                if job is None:
                    raise DataInvariantError(
                        f"listing job {row.job_id} does not exist"
                    )
                await self._append_ledger(
                    session,
                    operation_id=f"refund:{row.id}",
                    user_id=job.user_id,
                    amount=-row.reserved_cost,
                )
                self._add_job_event(
                    session,
                    job_id=row.job_id,
                    event_type=TaskEventType.IMAGE_FAILED,
                    data={
                        "item_id": row.id,
                        "image_type": row.image_type,
                        "error_code": safe_code,
                        "error": safe_detail,
                    },
                )
                await session.flush()
                await self._release_next_item(session, row.job_id)
                job_status = await self._aggregate_job(session, row.job_id)
                if job_status is not None:
                    self._add_terminal_job_event(
                        session, row.job_id, job_status
                    )

    async def mark_submission_uncertain(
        self, item_id: str, worker_id: str, error_detail: str
    ) -> None:
        async with self._session_factory() as session:
            async with session.begin():
                row = await self._owned_transition(
                    session,
                    item_id,
                    worker_id,
                    (GenerationItemStatus.SUBMITTING,),
                    GenerationItemStatus.SUBMISSION_UNCERTAIN,
                    worker_id=None,
                    lease_expires_at=None,
                    heartbeat_at=None,
                    error_code="submission_uncertain",
                    error_detail=error_detail[:_SAFE_ERROR_LIMIT],
                )
                self._add_job_event(
                    session,
                    job_id=row.job_id,
                    event_type=TaskEventType.IMAGE_FAILED,
                    data={
                        "item_id": row.id,
                        "image_type": row.image_type,
                        "error_code": "submission_uncertain",
                        "error": "Provider submission outcome requires manual review",
                    },
                )
                await session.flush()
                await self._release_next_item(session, row.job_id)
                job_status = await self._aggregate_job(session, row.job_id)
                if job_status is not None:
                    self._add_terminal_job_event(
                        session, row.job_id, job_status
                    )

    async def heartbeat(
        self, item_id: str, worker_id: str, lease_seconds: int
    ) -> None:
        if lease_seconds <= 0:
            raise ValueError("lease_seconds must be positive")
        now = datetime.now(UTC)
        async with self._session_factory() as session:
            result = await session.execute(
                update(GenerationItemRow)
                .where(
                    GenerationItemRow.id == item_id,
                    GenerationItemRow.worker_id == worker_id,
                    GenerationItemRow.status.in_(_ACTIVE_STATUSES),
                )
                .values(
                    heartbeat_at=now,
                    lease_expires_at=now + timedelta(seconds=lease_seconds),
                )
            )
            self._require_one(
                getattr(result, "rowcount", None), item_id, "heartbeat"
            )
            await session.commit()

    async def cancel_item(self, item_id: str, user_id: str) -> None:
        async with self._session_factory() as session:
            async with session.begin():
                result = (
                    await session.execute(
                        select(GenerationItemRow, ListingJobRow)
                        .join(ListingJobRow, ListingJobRow.id == GenerationItemRow.job_id)
                        .where(GenerationItemRow.id == item_id)
                    )
                ).one_or_none()
                if result is None:
                    raise ConcurrentTaskMutation(
                        f"generation item {item_id} does not exist"
                    )
                row, job = result
                if job.user_id != user_id:
                    raise ConcurrentTaskMutation(
                        f"generation item {item_id} is not owned by user {user_id}"
                    )
                mutation = await session.execute(
                    update(GenerationItemRow)
                    .where(
                        GenerationItemRow.id == item_id,
                        GenerationItemRow.status.in_(
                            (
                                GenerationItemStatus.WAITING.value,
                                GenerationItemStatus.QUEUED.value,
                            )
                        ),
                    )
                    .values(
                        status=GenerationItemStatus.CANCELLED.value,
                        error_code="cancelled",
                        error_detail="Cancelled before provider submission",
                    )
                )
                self._require_one(
                    getattr(mutation, "rowcount", None), item_id, "cancel"
                )
                await self._append_ledger(
                    session,
                    operation_id=f"refund:{row.id}",
                    user_id=job.user_id,
                    amount=-row.reserved_cost,
                )
                self._add_job_event(
                    session,
                    job_id=row.job_id,
                    event_type=TaskEventType.IMAGE_FAILED,
                    data={
                        "item_id": row.id,
                        "image_type": row.image_type,
                        "error_code": "cancelled",
                        "error": "Cancelled before provider submission",
                    },
                )
                await session.flush()
                await self._release_next_item(session, row.job_id)
                job_status = await self._aggregate_job(session, row.job_id)
                if job_status is not None:
                    self._add_terminal_job_event(
                        session, row.job_id, job_status
                    )

    @staticmethod
    def _to_work_item(
        row: GenerationItemRow, user_id: str
    ) -> GenerationWorkItem:
        size_parts = row.size.split("x", maxsplit=1)
        if len(size_parts) != 2:
            raise DataInvariantError(
                f"generation item {row.id} has invalid size snapshot"
            )
        try:
            references = tuple(
                ReferenceSnapshot(
                    source=ReferenceSource(value["source"]),
                    object_key=value["object_key"],
                    role=value["role"],
                    order=int(value["order"]),
                )
                for value in row.reference_snapshot
            )
            size = (int(size_parts[0]), int(size_parts[1]))
            spec = GenerationItemSpec(
                item_id=row.id,
                operation_id=row.operation_id,
                sequence=row.sequence,
                image_type=row.image_type,
                operation_type=OperationType(row.operation_type),
                render_tier=RenderTier(row.render_tier),
                final_prompt=row.final_prompt,
                model=ModelName(row.model),
                ratio=row.ratio,
                size=size,
                quality=row.quality,
                seed=row.seed,
                references=references,
                reserved_cost=row.reserved_cost,
            )
        except (KeyError, TypeError, ValueError) as exc:
            raise DataInvariantError(
                f"generation item {row.id} has an invalid immutable snapshot"
            ) from exc
        return GenerationWorkItem(
            job_id=row.job_id,
            user_id=user_id,
            spec=spec,
            status=GenerationItemStatus(row.status),
            provider_task_id=row.provider_task_id,
            worker_id=row.worker_id,
            lease_expires_at=row.lease_expires_at,
        )

    @staticmethod
    def _lease_is_expired(
        lease_expires_at: datetime | None, now: datetime
    ) -> bool:
        if lease_expires_at is None:
            return True
        if lease_expires_at.tzinfo is None:
            lease_expires_at = lease_expires_at.replace(tzinfo=UTC)
        return lease_expires_at <= now

    async def _require_user_capacity(
        self, session: AsyncSession, job_id: str
    ) -> None:
        job = await session.get(ListingJobRow, job_id)
        if job is None:
            raise DataInvariantError(f"listing job {job_id} does not exist")
        await self._lock_user(session, job.user_id)
        active_count = await session.scalar(
            select(func.count())
            .select_from(GenerationItemRow)
            .join(ListingJobRow, ListingJobRow.id == GenerationItemRow.job_id)
            .where(
                ListingJobRow.user_id == job.user_id,
                GenerationItemRow.status.in_(_ACTIVE_STATUSES),
            )
        )
        if active_count is not None and active_count >= 2:
            raise ConcurrentTaskMutation(
                f"user {job.user_id} already has two in-flight generation items"
            )

    async def _owned_transition(
        self,
        session: AsyncSession,
        item_id: str,
        owner_id: str,
        expected: tuple[GenerationItemStatus, ...],
        target: GenerationItemStatus,
        **values: object,
    ) -> GenerationItemRow:
        row = await session.get(GenerationItemRow, item_id)
        if row is None or GenerationItemStatus(row.status) not in expected:
            current = None if row is None else row.status
            raise ConcurrentTaskMutation(
                f"generation item {item_id} cannot transition from {current} to {target}"
            )
        mutation = await session.execute(
            update(GenerationItemRow)
            .where(
                GenerationItemRow.id == item_id,
                GenerationItemRow.status == row.status,
                GenerationItemRow.worker_id == owner_id,
            )
            .values(status=target.value, **values)
        )
        self._require_one(
            getattr(mutation, "rowcount", None), item_id, target.value
        )
        for name, value in values.items():
            setattr(row, name, value)
        row.status = target.value
        return row

    @staticmethod
    def _require_one(
        rowcount: int | None, item_id: str, operation: str
    ) -> None:
        if rowcount != 1:
            raise ConcurrentTaskMutation(
                f"generation item {item_id} lost compare-and-set during {operation}"
            )

    async def _release_next_item(
        self, session: AsyncSession, job_id: str
    ) -> None:
        queued_count = await session.scalar(
            select(func.count())
            .select_from(GenerationItemRow)
            .where(
                GenerationItemRow.job_id == job_id,
                GenerationItemRow.status == GenerationItemStatus.QUEUED.value,
            )
        )
        if queued_count:
            return
        job = await session.get(ListingJobRow, job_id)
        if job is None:
            raise DataInvariantError(f"listing job {job_id} does not exist")
        active_count = await session.scalar(
            select(func.count())
            .select_from(GenerationItemRow)
            .join(ListingJobRow, ListingJobRow.id == GenerationItemRow.job_id)
            .where(
                ListingJobRow.user_id == job.user_id,
                GenerationItemRow.status.in_(_ACTIVE_STATUSES),
            )
        )
        if active_count is not None and active_count >= 2:
            return
        next_item = await session.scalar(
            select(GenerationItemRow)
            .where(
                GenerationItemRow.job_id == job_id,
                GenerationItemRow.status == GenerationItemStatus.WAITING.value,
            )
            .order_by(GenerationItemRow.sequence)
            .limit(1)
            .with_for_update()
        )
        if next_item is None:
            return
        mutation = await session.execute(
            update(GenerationItemRow)
            .where(
                GenerationItemRow.id == next_item.id,
                GenerationItemRow.status == GenerationItemStatus.WAITING.value,
            )
            .values(status=GenerationItemStatus.QUEUED.value)
        )
        self._require_one(
            getattr(mutation, "rowcount", None), next_item.id, "release"
        )
        context = await self._job_message_context(session, job_id)
        message = TaskMessage(
            schema_version=1,
            message_id=uuid4().hex,
            trace_id=context["trace_id"],
            request_id=context["request_id"],
            job_id=job_id,
            item_id=next_item.id,
            operation_id=next_item.operation_id,
            operation_type=OperationType(next_item.operation_type),
            user_id=job.user_id,
            created_at=datetime.now(UTC),
        )
        session.add(
            OutboxEventRow(
                id=uuid4().hex,
                aggregate_type="generation_item",
                aggregate_id=next_item.id,
                event_type="generation_item.queued",
                payload=message.to_redis_fields(),
                publish_attempts=0,
            )
        )

    @staticmethod
    async def _job_message_context(
        session: AsyncSession, job_id: str
    ) -> dict[str, str]:
        payload = await session.scalar(
            select(OutboxEventRow.payload)
            .join(
                GenerationItemRow,
                GenerationItemRow.id == OutboxEventRow.aggregate_id,
            )
            .where(GenerationItemRow.job_id == job_id)
            .order_by(OutboxEventRow.created_at, OutboxEventRow.id)
            .limit(1)
        )
        if payload is None:
            raise DataInvariantError(
                f"listing job {job_id} has no task message context"
            )
        trace_id = payload.get("trace_id")
        request_id = payload.get("request_id")
        if not isinstance(trace_id, str) or not isinstance(request_id, str):
            raise DataInvariantError(
                f"listing job {job_id} has invalid task message context"
            )
        return {"trace_id": trace_id, "request_id": request_id}

    @staticmethod
    async def _append_ledger(
        session: AsyncSession,
        *,
        operation_id: str,
        user_id: str,
        amount: Decimal,
    ) -> None:
        existing = await session.scalar(
            select(CostLedgerEntry).where(
                CostLedgerEntry.operation_id == operation_id
            )
        )
        if existing is not None:
            if existing.user_id != user_id or existing.amount != amount:
                raise DataInvariantError(
                    f"ledger operation {operation_id} conflicts with persisted entry"
                )
            return
        session.add(
            CostLedgerEntry(
                operation_id=operation_id,
                user_id=user_id,
                amount=amount,
            )
        )

    @staticmethod
    def _add_job_event(
        session: AsyncSession,
        *,
        job_id: str,
        event_type: TaskEventType,
        data: dict[str, object],
    ) -> None:
        session.add(
            OutboxEventRow(
                id=uuid4().hex,
                aggregate_type="listing_job_event",
                aggregate_id=job_id,
                event_type=f"listing_job.{event_type.value}",
                payload={
                    "job_id": job_id,
                    "event_type": event_type.value,
                    "data": data,
                },
                publish_attempts=0,
            )
        )

    @classmethod
    def _add_terminal_job_event(
        cls,
        session: AsyncSession,
        job_id: str,
        job_status: str,
    ) -> None:
        event_type = (
            TaskEventType.TASK_FAILED
            if job_status == "失败"
            else TaskEventType.TASK_COMPLETED
        )
        cls._add_job_event(
            session,
            job_id=job_id,
            event_type=event_type,
            data={"status": job_status},
        )

    @staticmethod
    async def _aggregate_job(
        session: AsyncSession, job_id: str
    ) -> str | None:
        rows = (
            await session.execute(
                select(GenerationItemRow).where(
                    GenerationItemRow.job_id == job_id
                )
            )
        ).scalars().all()
        if not rows or any(
            not is_terminal(GenerationItemStatus(row.status)) for row in rows
        ):
            return None
        generated_count = sum(
            row.status == GenerationItemStatus.GENERATED.value for row in rows
        )
        if generated_count == len(rows):
            status = "完成"
        elif generated_count:
            status = "部分完成"
        else:
            status = "失败"
        total_cost = await session.scalar(
            select(func.coalesce(func.sum(ListingImageRow.cost), 0)).where(
                ListingImageRow.job_id == job_id,
                ListingImageRow.status == "成功",
            )
        )
        error = next(
            (
                row.error_detail
                for row in rows
                if row.error_detail is not None
            ),
            None,
        )
        job = await session.get(ListingJobRow, job_id)
        if job is None:
            raise DataInvariantError(f"listing job {job_id} does not exist")
        job.status = status
        job.total_cost = Decimal(str(total_cost))
        job.error = error
        job.completed_at = datetime.now(UTC)
        return status

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

    async def _require_budget(
        self,
        session: AsyncSession,
        submission: JobSubmission,
    ) -> None:
        start = month_start_utc()
        await session.execute(
            select(CostLedgerEntry.id)
            .where(CostLedgerEntry.created_at >= start)
            .order_by(CostLedgerEntry.id)
            .with_for_update()
        )
        total = func.coalesce(func.sum(CostLedgerEntry.amount), 0)
        user_used = await session.scalar(
            select(total).where(
                CostLedgerEntry.user_id == submission.job.user_id,
                CostLedgerEntry.created_at >= start,
            )
        )
        company_used = await session.scalar(
            select(total).where(CostLedgerEntry.created_at >= start)
        )
        estimate = sum(
            (item.reserved_cost for item in submission.items),
            start=Decimal("0"),
        )
        self._budget_policy.check(
            estimate,
            BudgetSnapshot(
                user_month_used=Decimal(str(user_used)),
                user_monthly_quota=self._user_quota,
                company_month_used=Decimal(str(company_used)),
                company_monthly_budget=self._company_budget,
            ),
        )

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
