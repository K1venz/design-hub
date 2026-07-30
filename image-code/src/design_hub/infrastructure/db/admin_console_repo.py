from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any
from uuid import uuid4

from sqlalchemy import (
    String,
    and_,
    case,
    cast,
    desc,
    func,
    or_,
    select,
    union_all,
)
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from sqlalchemy.orm import selectinload

from design_hub.domain.admin import (
    AdminAction,
    ModelCallStatus,
    ModelModality,
    ModerationReason,
    ModerationStatus,
)
from design_hub.domain.enums import ModelName, Role
from design_hub.domain.errors import DomainError, NotFoundError
from design_hub.infrastructure.db.models import (
    AdminAuditLogRow,
    AppUser,
    ChatSessionRow,
    GenerationItemRow,
    ListingImageRow,
    ListingJobRow,
    ModelCallRow,
)
from design_hub.ports.admin_console import (
    AdminAuditEntry,
    AdminAuditFilter,
    AdminConsoleRepository,
    AdminGenerationItem,
    AdminImageFilter,
    AdminImageSummary,
    AdminJobDetail,
    AdminJobFilter,
    AdminJobImage,
    AdminJobInput,
    AdminJobSummary,
    AdminOverview,
    AdminUserDetail,
    AdminUserFilter,
    AdminUserSummary,
    DateRange,
    ModelCallDetail,
    ModelCallFilter,
    ModelCallSummary,
    Page,
)

_IMAGE_STALE_AFTER = timedelta(minutes=6)
_FOUR_K_IMAGE_STALE_AFTER = timedelta(minutes=31)
_CHAT_STALE_AFTER = timedelta(minutes=2)


class SqlAlchemyAdminConsoleRepository(AdminConsoleRepository):
    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession],
    ) -> None:
        self._session_factory = session_factory

    async def overview(self, date_range: DateRange) -> AdminOverview:
        now = datetime.now(UTC)
        status = self._effective_call_status(now)
        call_range = (
            ModelCallRow.started_at >= date_range.start,
            ModelCallRow.started_at < date_range.end,
        )
        image_range = (
            ListingImageRow.created_at >= date_range.start,
            ListingImageRow.created_at < date_range.end,
        )
        async with self._session_factory() as session:
            registered_users = await self._count(
                session,
                select(func.count()).select_from(AppUser),
            )
            active_users_query = union_all(
                select(ListingJobRow.user_id.label("user_id")).where(
                    ListingJobRow.created_at >= date_range.start,
                    ListingJobRow.created_at < date_range.end,
                ),
                select(ChatSessionRow.user_id.label("user_id")).where(
                    ChatSessionRow.updated_at >= date_range.start,
                    ChatSessionRow.updated_at < date_range.end,
                ),
                select(ModelCallRow.user_id.label("user_id")).where(*call_range),
            ).subquery()
            active_users = await self._count(
                session,
                select(func.count(func.distinct(active_users_query.c.user_id))),
            )
            jobs = await self._count(
                session,
                select(func.count())
                .select_from(ListingJobRow)
                .where(
                    ListingJobRow.created_at >= date_range.start,
                    ListingJobRow.created_at < date_range.end,
                ),
            )
            image_metrics = (
                await session.execute(
                    select(
                        func.coalesce(
                            func.sum(
                                case(
                                    (ListingImageRow.status == "成功", 1),
                                    else_=0,
                                )
                            ),
                            0,
                        ),
                        func.coalesce(
                            func.sum(
                                case(
                                    (
                                        ListingImageRow.status == "成功",
                                        ListingImageRow.cost,
                                    ),
                                    else_=0,
                                )
                            ),
                            0,
                        ),
                    ).where(*image_range)
                )
            ).one()
            call_metrics = (
                await session.execute(
                    select(
                        self._sum_when(
                            ModelCallRow.modality == ModelModality.IMAGE.value
                        ),
                        self._sum_when(
                            and_(
                                ModelCallRow.modality
                                == ModelModality.IMAGE.value,
                                status == ModelCallStatus.SUCCEEDED.value,
                            )
                        ),
                        self._sum_when(
                            and_(
                                ModelCallRow.modality
                                == ModelModality.IMAGE.value,
                                status == ModelCallStatus.FAILED.value,
                            )
                        ),
                        self._sum_when(
                            and_(
                                ModelCallRow.modality
                                == ModelModality.IMAGE.value,
                                status == ModelCallStatus.UNCERTAIN.value,
                            )
                        ),
                        self._sum_when(
                            and_(
                                ModelCallRow.modality
                                == ModelModality.IMAGE.value,
                                ModelCallRow.attempt_no > 1,
                            )
                        ),
                        self._sum_when(
                            ModelCallRow.modality == ModelModality.CHAT.value
                        ),
                        func.coalesce(
                            func.sum(
                                case(
                                    (
                                        ModelCallRow.modality
                                        == ModelModality.CHAT.value,
                                        ModelCallRow.input_tokens,
                                    ),
                                    else_=0,
                                )
                            ),
                            0,
                        ),
                        func.coalesce(
                            func.sum(
                                case(
                                    (
                                        ModelCallRow.modality
                                        == ModelModality.CHAT.value,
                                        ModelCallRow.output_tokens,
                                    ),
                                    else_=0,
                                )
                            ),
                            0,
                        ),
                        func.coalesce(
                            func.sum(
                                case(
                                    (
                                        ModelCallRow.modality
                                        == ModelModality.CHAT.value,
                                        ModelCallRow.total_tokens,
                                    ),
                                    else_=0,
                                )
                            ),
                            0,
                        ),
                        func.avg(ModelCallRow.latency_ms),
                        self._sum_when(
                            status == ModelCallStatus.FAILED.value
                        ),
                        func.count(ModelCallRow.id),
                    ).where(*call_range)
                )
            ).one()
        total_calls = int(call_metrics[11] or 0)
        failed_calls = int(call_metrics[10] or 0)
        return AdminOverview(
            start=date_range.start,
            end=date_range.end,
            registered_users=registered_users,
            active_users=active_users,
            jobs=jobs,
            successful_images=int(image_metrics[0]),
            image_calls=int(call_metrics[0]),
            image_succeeded=int(call_metrics[1]),
            image_failed=int(call_metrics[2]),
            image_uncertain=int(call_metrics[3]),
            image_retries=int(call_metrics[4]),
            chat_calls=int(call_metrics[5]),
            chat_input_tokens=int(call_metrics[6]),
            chat_output_tokens=int(call_metrics[7]),
            chat_total_tokens=int(call_metrics[8]),
            platform_cost=Decimal(image_metrics[1]),
            average_latency_ms=(
                float(call_metrics[9])
                if call_metrics[9] is not None
                else None
            ),
            failure_rate=(
                failed_calls / total_calls if total_calls else 0.0
            ),
        )

    async def list_users(
        self,
        filters: AdminUserFilter,
        *,
        limit: int,
        offset: int,
    ) -> Page[AdminUserSummary]:
        conditions = self._user_conditions(filters)
        metrics = self._user_metrics()
        async with self._session_factory() as session:
            total = await self._count(
                session,
                select(func.count()).select_from(AppUser).where(*conditions),
            )
            statement = (
                select(AppUser, *metrics["columns"])
                .select_from(AppUser)
                .outerjoin(
                    metrics["jobs"],
                    metrics["jobs"].c.user_id == cast(AppUser.id, String),
                )
                .outerjoin(
                    metrics["images"],
                    metrics["images"].c.user_id == cast(AppUser.id, String),
                )
                .outerjoin(
                    metrics["calls"],
                    metrics["calls"].c.user_id == cast(AppUser.id, String),
                )
                .outerjoin(
                    metrics["chats"],
                    metrics["chats"].c.user_id == cast(AppUser.id, String),
                )
                .where(*conditions)
                .order_by(desc(AppUser.created_at), desc(AppUser.id))
                .limit(limit)
                .offset(offset)
            )
            rows = (await session.execute(statement)).all()
        return Page(
            items=tuple(self._user_summary(row) for row in rows),
            total=total,
            limit=limit,
            offset=offset,
        )

    async def get_user(self, user_id: int) -> AdminUserDetail | None:
        metrics = self._user_metrics()
        async with self._session_factory() as session:
            statement = (
                select(AppUser, *metrics["columns"])
                .select_from(AppUser)
                .outerjoin(
                    metrics["jobs"],
                    metrics["jobs"].c.user_id == cast(AppUser.id, String),
                )
                .outerjoin(
                    metrics["images"],
                    metrics["images"].c.user_id == cast(AppUser.id, String),
                )
                .outerjoin(
                    metrics["calls"],
                    metrics["calls"].c.user_id == cast(AppUser.id, String),
                )
                .outerjoin(
                    metrics["chats"],
                    metrics["chats"].c.user_id == cast(AppUser.id, String),
                )
                .where(AppUser.id == user_id)
            )
            row = (await session.execute(statement)).one_or_none()
        if row is None:
            return None
        summary = self._user_summary(row)
        user: AppUser = row[0]
        return AdminUserDetail(
            **summary.__dict__,
            disabled_at=user.disabled_at,
            disabled_by=user.disabled_by,
            disabled_reason=user.disabled_reason,
        )

    async def list_jobs(
        self,
        filters: AdminJobFilter,
        *,
        limit: int,
        offset: int,
    ) -> Page[AdminJobSummary]:
        conditions = self._job_conditions(filters)
        async with self._session_factory() as session:
            total = await self._count(
                session,
                select(func.count(func.distinct(ListingJobRow.id)))
                .select_from(ListingJobRow)
                .outerjoin(
                    GenerationItemRow,
                    GenerationItemRow.job_id == ListingJobRow.id,
                )
                .where(*conditions),
            )
            statement = (
                select(
                    ListingJobRow,
                    AppUser,
                    func.min(GenerationItemRow.operation_type),
                    func.min(GenerationItemRow.model),
                    func.count(
                        func.distinct(
                            case(
                                (
                                    ListingImageRow.status == "成功",
                                    ListingImageRow.id,
                                )
                            )
                        )
                    ),
                    func.min(
                        case(
                            (
                                ListingImageRow.status == "成功",
                                ListingImageRow.image_key,
                            )
                        )
                    ),
                )
                .select_from(ListingJobRow)
                .join(
                    AppUser,
                    cast(AppUser.id, String) == ListingJobRow.user_id,
                )
                .outerjoin(
                    ListingImageRow,
                    ListingImageRow.job_id == ListingJobRow.id,
                )
                .outerjoin(
                    GenerationItemRow,
                    GenerationItemRow.job_id == ListingJobRow.id,
                )
                .where(*conditions)
                .group_by(ListingJobRow.id, AppUser.id)
                .order_by(
                    desc(ListingJobRow.created_at),
                    desc(ListingJobRow.id),
                )
                .limit(limit)
                .offset(offset)
            )
            rows = (await session.execute(statement)).all()
        return Page(
            items=tuple(self._job_summary(row) for row in rows),
            total=total,
            limit=limit,
            offset=offset,
        )

    async def get_job(self, job_id: str) -> AdminJobDetail | None:
        async with self._session_factory() as session:
            statement = (
                select(ListingJobRow)
                .where(ListingJobRow.id == job_id)
                .options(
                    selectinload(ListingJobRow.images),
                    selectinload(ListingJobRow.inputs),
                    selectinload(ListingJobRow.generation_items),
                )
            )
            job = (await session.execute(statement)).scalar_one_or_none()
            if job is None:
                return None
            user = await session.get(AppUser, int(job.user_id))
            if user is None:
                raise RuntimeError(f"任务 {job.id} 的用户不存在")
        operation_type = self._single_value(
            {item.operation_type for item in job.generation_items},
            label=f"任务 {job.id} 的操作类型",
        )
        model = self._single_value(
            {item.model for item in job.generation_items},
            label=f"任务 {job.id} 的模型",
        )
        images = sorted(job.images, key=lambda item: item.id)
        successes = [item for item in images if item.status == "成功"]
        return AdminJobDetail(
            job_id=job.id,
            user_id=user.id,
            user_email=user.email,
            user_name=user.name,
            status=job.status,
            operation_type=operation_type,
            model=model,
            ratio=job.ratio,
            size=job.size,
            requested_images=job.n,
            successful_images=len(successes),
            total_cost=job.total_cost,
            first_image_key=(
                successes[0].image_key if successes else None
            ),
            created_at=job.created_at,
            completed_at=job.completed_at,
            prompt=job.prompt,
            modifiers=dict(job.modifiers),
            error=job.error,
            inputs=tuple(
                AdminJobInput(key=item.upload_key, role=item.role)
                for item in sorted(job.inputs, key=lambda item: item.ord)
            ),
            images=tuple(self._job_image(item) for item in images),
            generation_items=tuple(
                AdminGenerationItem(
                    item_id=item.id,
                    operation_type=item.operation_type,
                    model=item.model,
                    status=item.status,
                    final_prompt=item.final_prompt,
                    attempt_count=item.attempt_count,
                    error_code=item.error_code,
                    error_detail=item.error_detail,
                )
                for item in sorted(
                    job.generation_items,
                    key=lambda item: item.sequence,
                )
            ),
        )

    async def list_images(
        self,
        filters: AdminImageFilter,
        *,
        limit: int,
        offset: int,
    ) -> Page[AdminImageSummary]:
        conditions = self._image_conditions(filters)
        async with self._session_factory() as session:
            total = await self._count(
                session,
                select(func.count(func.distinct(ListingImageRow.id)))
                .select_from(ListingImageRow)
                .join(
                    ListingJobRow,
                    ListingJobRow.id == ListingImageRow.job_id,
                )
                .outerjoin(
                    GenerationItemRow,
                    GenerationItemRow.job_id == ListingJobRow.id,
                )
                .where(*conditions),
            )
            statement = (
                select(
                    ListingImageRow,
                    ListingJobRow,
                    AppUser,
                    func.min(GenerationItemRow.operation_type),
                    func.min(GenerationItemRow.model),
                )
                .select_from(ListingImageRow)
                .join(
                    ListingJobRow,
                    ListingJobRow.id == ListingImageRow.job_id,
                )
                .join(
                    AppUser,
                    cast(AppUser.id, String) == ListingJobRow.user_id,
                )
                .outerjoin(
                    GenerationItemRow,
                    GenerationItemRow.job_id == ListingJobRow.id,
                )
                .where(*conditions)
                .group_by(
                    ListingImageRow.id,
                    ListingJobRow.id,
                    AppUser.id,
                )
                .order_by(
                    desc(ListingImageRow.created_at),
                    desc(ListingImageRow.id),
                )
                .limit(limit)
                .offset(offset)
            )
            rows = (await session.execute(statement)).all()
        return Page(
            items=tuple(self._image_summary(row) for row in rows),
            total=total,
            limit=limit,
            offset=offset,
        )

    async def summarize_model_calls(
        self,
        filters: ModelCallFilter,
    ) -> tuple[ModelCallSummary, ...]:
        now = datetime.now(UTC)
        status = self._effective_call_status(now)
        conditions = self._call_conditions(filters, status)
        async with self._session_factory() as session:
            statement = (
                select(
                    ModelCallRow.provider,
                    ModelCallRow.model,
                    ModelCallRow.modality,
                    func.count(ModelCallRow.id),
                    self._sum_when(
                        status == ModelCallStatus.SUCCEEDED.value
                    ),
                    self._sum_when(
                        status == ModelCallStatus.FAILED.value
                    ),
                    self._sum_when(
                        status == ModelCallStatus.UNCERTAIN.value
                    ),
                    self._sum_when(
                        status == ModelCallStatus.INTERRUPTED.value
                    ),
                    self._sum_when(ModelCallRow.attempt_no > 1),
                    func.coalesce(func.sum(ModelCallRow.input_tokens), 0),
                    func.coalesce(func.sum(ModelCallRow.output_tokens), 0),
                    func.coalesce(func.sum(ModelCallRow.total_tokens), 0),
                    func.coalesce(func.sum(ModelCallRow.platform_cost), 0),
                    func.avg(ModelCallRow.latency_ms),
                )
                .where(*conditions)
                .group_by(
                    ModelCallRow.provider,
                    ModelCallRow.model,
                    ModelCallRow.modality,
                )
                .order_by(
                    desc(func.count(ModelCallRow.id)),
                    ModelCallRow.model,
                )
            )
            rows = (await session.execute(statement)).all()
        return tuple(
            ModelCallSummary(
                provider=row[0],
                model=row[1],
                modality=row[2],
                operation_type=filters.operation_type,
                calls=int(row[3]),
                succeeded=int(row[4]),
                failed=int(row[5]),
                uncertain=int(row[6]),
                interrupted=int(row[7]),
                retries=int(row[8]),
                input_tokens=int(row[9]),
                output_tokens=int(row[10]),
                total_tokens=int(row[11]),
                platform_cost=Decimal(row[12]),
                average_latency_ms=(
                    float(row[13]) if row[13] is not None else None
                ),
            )
            for row in rows
        )

    async def list_model_calls(
        self,
        filters: ModelCallFilter,
        *,
        limit: int,
        offset: int,
    ) -> Page[ModelCallDetail]:
        now = datetime.now(UTC)
        status = self._effective_call_status(now)
        conditions = self._call_conditions(filters, status)
        async with self._session_factory() as session:
            total = await self._count(
                session,
                select(func.count())
                .select_from(ModelCallRow)
                .where(*conditions),
            )
            statement = (
                select(ModelCallRow, AppUser, status)
                .join(
                    AppUser,
                    cast(AppUser.id, String) == ModelCallRow.user_id,
                )
                .where(*conditions)
                .order_by(
                    desc(ModelCallRow.started_at),
                    desc(ModelCallRow.id),
                )
                .limit(limit)
                .offset(offset)
            )
            rows = (await session.execute(statement)).all()
        return Page(
            items=tuple(self._call_detail(row) for row in rows),
            total=total,
            limit=limit,
            offset=offset,
        )

    async def list_audit_logs(
        self,
        filters: AdminAuditFilter,
        *,
        limit: int,
        offset: int,
    ) -> Page[AdminAuditEntry]:
        conditions: list[Any] = []
        if filters.actor_user_id is not None:
            conditions.append(
                AdminAuditLogRow.actor_user_id == filters.actor_user_id
            )
        if filters.action is not None:
            conditions.append(AdminAuditLogRow.action == filters.action)
        if filters.target_type is not None:
            conditions.append(
                AdminAuditLogRow.target_type == filters.target_type
            )
        self._append_date_conditions(
            conditions,
            AdminAuditLogRow.created_at,
            filters.date_range,
        )
        async with self._session_factory() as session:
            total = await self._count(
                session,
                select(func.count())
                .select_from(AdminAuditLogRow)
                .where(*conditions),
            )
            statement = (
                select(AdminAuditLogRow, AppUser)
                .join(
                    AppUser,
                    AppUser.id == AdminAuditLogRow.actor_user_id,
                )
                .where(*conditions)
                .order_by(
                    desc(AdminAuditLogRow.created_at),
                    desc(AdminAuditLogRow.id),
                )
                .limit(limit)
                .offset(offset)
            )
            rows = (await session.execute(statement)).all()
        return Page(
            items=tuple(
                AdminAuditEntry(
                    audit_id=audit.id,
                    actor_user_id=actor.id,
                    actor_email=actor.email,
                    action=audit.action,
                    target_type=audit.target_type,
                    target_id=audit.target_id,
                    before=audit.before,
                    after=audit.after,
                    reason=audit.reason,
                    created_at=audit.created_at,
                )
                for audit, actor in rows
            ),
            total=total,
            limit=limit,
            offset=offset,
        )

    async def set_image_moderation(
        self,
        *,
        actor_id: int,
        image_id: int,
        status: ModerationStatus,
        reason: ModerationReason | None,
        note: str | None,
    ) -> AdminJobImage:
        async with self._session_factory() as session:
            async with session.begin():
                image = (
                    await session.execute(
                        select(ListingImageRow)
                        .where(ListingImageRow.id == image_id)
                        .with_for_update()
                    )
                ).scalar_one_or_none()
                if image is None:
                    raise NotFoundError("图片不存在")
                if image.moderation_status == status.value:
                    raise DomainError("图片审核状态没有变化")
                before: dict[str, object] = {
                    "status": image.moderation_status
                }
                if image.moderation_status == ModerationStatus.BLOCKED.value:
                    before.update(
                        {
                            "reason": image.moderation_reason,
                            "note": image.moderation_note,
                        }
                    )
                if status is ModerationStatus.BLOCKED:
                    assert reason is not None
                    image.moderation_reason = reason.value
                    image.moderation_note = note
                    after: dict[str, object] = {
                        "status": status.value,
                        "reason": reason.value,
                        "note": note,
                    }
                else:
                    image.moderation_reason = None
                    image.moderation_note = None
                    after = {"status": status.value}
                image.moderation_status = status.value
                image.moderated_by = actor_id
                image.moderated_at = datetime.now(UTC)
                session.add(
                    AdminAuditLogRow(
                        id=uuid4().hex,
                        actor_user_id=actor_id,
                        action=AdminAction.IMAGE_MODERATION_UPDATE.value,
                        target_type="image",
                        target_id=str(image_id),
                        before=before,
                        after=after,
                        reason=(
                            reason.value if reason is not None else None
                        ),
                    )
                )
                await session.flush()
                result = self._job_image(image)
        return result

    @staticmethod
    async def _count(session: AsyncSession, statement: Any) -> int:
        value = await session.scalar(statement)
        return int(value or 0)

    @staticmethod
    def _sum_when(condition: Any) -> Any:
        return func.coalesce(
            func.sum(case((condition, 1), else_=0)),
            0,
        )

    @staticmethod
    def _effective_call_status(now: datetime) -> Any:
        return case(
            (
                and_(
                    ModelCallRow.status == ModelCallStatus.STARTED.value,
                    or_(
                        and_(
                            ModelCallRow.modality
                            == ModelModality.IMAGE.value,
                            or_(
                                and_(
                                    ModelCallRow.model
                                    == ModelName.GPT_IMAGE_2_4K.value,
                                    ModelCallRow.started_at
                                    < now - _FOUR_K_IMAGE_STALE_AFTER,
                                ),
                                and_(
                                    ModelCallRow.model
                                    != ModelName.GPT_IMAGE_2_4K.value,
                                    ModelCallRow.started_at
                                    < now - _IMAGE_STALE_AFTER,
                                ),
                            ),
                        ),
                        and_(
                            ModelCallRow.modality
                            == ModelModality.CHAT.value,
                            ModelCallRow.started_at
                            < now - _CHAT_STALE_AFTER,
                        ),
                    ),
                ),
                ModelCallStatus.UNCERTAIN.value,
            ),
            else_=ModelCallRow.status,
        )

    @staticmethod
    def _append_date_conditions(
        conditions: list[Any],
        column: Any,
        date_range: DateRange | None,
    ) -> None:
        if date_range is not None:
            conditions.extend(
                (
                    column >= date_range.start,
                    column < date_range.end,
                )
            )

    @staticmethod
    def _user_conditions(filters: AdminUserFilter) -> list[Any]:
        conditions: list[Any] = []
        if filters.q is not None:
            pattern = f"%{filters.q}%"
            conditions.append(
                or_(
                    AppUser.email.ilike(pattern),
                    AppUser.name.ilike(pattern),
                )
            )
        if filters.role is not None:
            conditions.append(AppUser.role == filters.role.value)
        if filters.enabled is not None:
            conditions.append(AppUser.enabled == filters.enabled)
        return conditions

    @staticmethod
    def _user_metrics() -> dict[str, Any]:
        jobs = (
            select(
                ListingJobRow.user_id.label("user_id"),
                func.count(ListingJobRow.id).label("jobs"),
                func.max(ListingJobRow.created_at).label("last_job_at"),
            )
            .group_by(ListingJobRow.user_id)
            .subquery()
        )
        images = (
            select(
                ListingJobRow.user_id.label("user_id"),
                func.coalesce(
                    func.sum(
                        case(
                            (ListingImageRow.status == "成功", 1),
                            else_=0,
                        )
                    ),
                    0,
                ).label("successful_images"),
                func.coalesce(
                    func.sum(
                        case(
                            (
                                ListingImageRow.status == "成功",
                                ListingImageRow.cost,
                            ),
                            else_=0,
                        )
                    ),
                    0,
                ).label("platform_cost"),
            )
            .join(
                ListingJobRow,
                ListingJobRow.id == ListingImageRow.job_id,
            )
            .group_by(ListingJobRow.user_id)
            .subquery()
        )
        calls = (
            select(
                ModelCallRow.user_id.label("user_id"),
                func.coalesce(
                    func.sum(
                        case(
                            (
                                ModelCallRow.modality
                                == ModelModality.IMAGE.value,
                                1,
                            ),
                            else_=0,
                        )
                    ),
                    0,
                ).label("image_calls"),
                func.coalesce(
                    func.sum(
                        case(
                            (
                                ModelCallRow.modality
                                == ModelModality.CHAT.value,
                                1,
                            ),
                            else_=0,
                        )
                    ),
                    0,
                ).label("chat_calls"),
                func.coalesce(
                    func.sum(
                        case(
                            (
                                ModelCallRow.modality
                                == ModelModality.CHAT.value,
                                ModelCallRow.total_tokens,
                            ),
                            else_=0,
                        )
                    ),
                    0,
                ).label("chat_total_tokens"),
                func.max(ModelCallRow.started_at).label("last_call_at"),
            )
            .group_by(ModelCallRow.user_id)
            .subquery()
        )
        chats = (
            select(
                ChatSessionRow.user_id.label("user_id"),
                func.max(ChatSessionRow.updated_at).label("last_chat_at"),
            )
            .group_by(ChatSessionRow.user_id)
            .subquery()
        )
        return {
            "jobs": jobs,
            "images": images,
            "calls": calls,
            "chats": chats,
            "columns": (
                jobs.c.jobs,
                jobs.c.last_job_at,
                images.c.successful_images,
                images.c.platform_cost,
                calls.c.image_calls,
                calls.c.chat_calls,
                calls.c.chat_total_tokens,
                calls.c.last_call_at,
                chats.c.last_chat_at,
            ),
        }

    @staticmethod
    def _user_summary(row: Any) -> AdminUserSummary:
        user: AppUser = row[0]
        activity = tuple(
            value for value in (row[2], row[8], row[9]) if value is not None
        )
        return AdminUserSummary(
            user_id=user.id,
            email=user.email,
            name=user.name,
            role=Role(user.role),
            enabled=user.enabled,
            created_at=user.created_at,
            last_activity_at=max(activity) if activity else None,
            jobs=int(row[1] or 0),
            successful_images=int(row[3] or 0),
            image_calls=int(row[5] or 0),
            chat_calls=int(row[6] or 0),
            chat_total_tokens=int(row[7] or 0),
            platform_cost=Decimal(row[4] or 0),
        )

    @classmethod
    def _job_conditions(cls, filters: AdminJobFilter) -> list[Any]:
        conditions: list[Any] = []
        if filters.user_id is not None:
            conditions.append(
                ListingJobRow.user_id == str(filters.user_id)
            )
        if filters.status is not None:
            conditions.append(ListingJobRow.status == filters.status)
        if filters.model is not None:
            conditions.append(GenerationItemRow.model == filters.model)
        if filters.operation_type is not None:
            conditions.append(
                GenerationItemRow.operation_type == filters.operation_type
            )
        cls._append_date_conditions(
            conditions,
            ListingJobRow.created_at,
            filters.date_range,
        )
        return conditions

    @staticmethod
    def _job_summary(row: Any) -> AdminJobSummary:
        job: ListingJobRow = row[0]
        user: AppUser = row[1]
        return AdminJobSummary(
            job_id=job.id,
            user_id=user.id,
            user_email=user.email,
            user_name=user.name,
            status=job.status,
            operation_type=row[2],
            model=row[3],
            ratio=job.ratio,
            size=job.size,
            requested_images=job.n,
            successful_images=int(row[4]),
            total_cost=job.total_cost,
            first_image_key=row[5],
            created_at=job.created_at,
            completed_at=job.completed_at,
        )

    @staticmethod
    def _job_image(image: ListingImageRow) -> AdminJobImage:
        return AdminJobImage(
            image_id=image.id,
            image_key=image.image_key,
            image_type=image.image_type,
            status=image.status,
            moderation_status=image.moderation_status,
            moderation_reason=image.moderation_reason,
            moderation_note=image.moderation_note,
            moderated_by=image.moderated_by,
            moderated_at=image.moderated_at,
            cost=image.cost,
            created_at=image.created_at,
        )

    @classmethod
    def _image_conditions(cls, filters: AdminImageFilter) -> list[Any]:
        conditions: list[Any] = []
        if filters.user_id is not None:
            conditions.append(
                ListingJobRow.user_id == str(filters.user_id)
            )
        if filters.model is not None:
            conditions.append(GenerationItemRow.model == filters.model)
        if filters.operation_type is not None:
            conditions.append(
                GenerationItemRow.operation_type == filters.operation_type
            )
        if filters.status is not None:
            conditions.append(ListingImageRow.status == filters.status)
        if filters.moderation_status is not None:
            conditions.append(
                ListingImageRow.moderation_status
                == filters.moderation_status
            )
        cls._append_date_conditions(
            conditions,
            ListingImageRow.created_at,
            filters.date_range,
        )
        return conditions

    @staticmethod
    def _image_summary(row: Any) -> AdminImageSummary:
        image: ListingImageRow = row[0]
        job: ListingJobRow = row[1]
        user: AppUser = row[2]
        return AdminImageSummary(
            image_id=image.id,
            image_key=image.image_key,
            job_id=job.id,
            user_id=user.id,
            user_email=user.email,
            user_name=user.name,
            image_type=image.image_type,
            status=image.status,
            moderation_status=image.moderation_status,
            moderation_reason=image.moderation_reason,
            moderation_note=image.moderation_note,
            moderated_by=image.moderated_by,
            moderated_at=image.moderated_at,
            operation_type=row[3],
            model=row[4],
            cost=image.cost,
            created_at=image.created_at,
        )

    @classmethod
    def _call_conditions(
        cls,
        filters: ModelCallFilter,
        effective_status: Any,
    ) -> list[Any]:
        conditions: list[Any] = []
        if filters.user_id is not None:
            conditions.append(ModelCallRow.user_id == str(filters.user_id))
        if filters.provider is not None:
            conditions.append(ModelCallRow.provider == filters.provider)
        if filters.model is not None:
            conditions.append(ModelCallRow.model == filters.model)
        if filters.modality is not None:
            conditions.append(ModelCallRow.modality == filters.modality)
        if filters.operation_type is not None:
            conditions.append(
                ModelCallRow.operation_type == filters.operation_type
            )
        if filters.status is not None:
            conditions.append(effective_status == filters.status)
        cls._append_date_conditions(
            conditions,
            ModelCallRow.started_at,
            filters.date_range,
        )
        return conditions

    @staticmethod
    def _call_detail(row: Any) -> ModelCallDetail:
        call: ModelCallRow = row[0]
        user: AppUser = row[1]
        return ModelCallDetail(
            call_id=call.id,
            user_id=user.id,
            user_email=user.email,
            provider=call.provider,
            model=call.model,
            modality=call.modality,
            operation_type=call.operation_type,
            attempt_no=call.attempt_no,
            status=row[2],
            provider_request_id=call.provider_request_id,
            input_tokens=call.input_tokens,
            output_tokens=call.output_tokens,
            total_tokens=call.total_tokens,
            input_text_tokens=call.input_text_tokens,
            input_image_tokens=call.input_image_tokens,
            output_image_tokens=call.output_image_tokens,
            error_code=call.error_code,
            error_detail=call.error_detail,
            job_id=call.job_id,
            generation_item_id=call.generation_item_id,
            chat_session_id=call.chat_session_id,
            started_at=call.started_at,
            completed_at=call.completed_at,
            latency_ms=call.latency_ms,
            platform_cost=call.platform_cost,
        )

    @staticmethod
    def _single_value(
        values: set[str],
        *,
        label: str,
    ) -> str | None:
        if not values:
            return None
        if len(values) != 1:
            raise RuntimeError(f"{label}不一致")
        return values.pop()
