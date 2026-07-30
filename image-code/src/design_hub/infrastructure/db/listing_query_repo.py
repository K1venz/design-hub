from decimal import Decimal

from sqlalchemy import desc, or_, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from sqlalchemy.orm import selectinload

from design_hub.infrastructure.db.models import (
    ListingImageRow,
    ListingJobInputRow,
    ListingJobRow,
)
from design_hub.ports.listing_query import (
    GeneratedImageSource,
    ListingHistoryQuery,
    ListingJobDetail,
    ListingJobImageView,
    ListingJobSummary,
)


class SqlAlchemyListingHistoryQuery(ListingHistoryQuery):
    """ListingHistory 读侧（ISSUE-0030）：按 user_id 隔离、时间倒序分页、详情含图+输入。"""

    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._session_factory = session_factory

    async def list_jobs(
        self, *, user_id: str, limit: int, offset: int, q: str | None = None
    ) -> list[ListingJobSummary]:
        async with self._session_factory() as session:
            stmt = select(ListingJobRow).where(ListingJobRow.user_id == user_id)
            if q:
                like = f"%{q}%"  # 模糊匹配 prompt / platform（ISSUE-0032 搜索）
                stmt = stmt.where(
                    or_(ListingJobRow.prompt.ilike(like), ListingJobRow.platform.ilike(like))
                )
            stmt = (
                # created_at 秒级精度，加 id 次级保证全序、分页稳定（无跨页重/漏）
                stmt.order_by(desc(ListingJobRow.created_at), desc(ListingJobRow.id))
                .limit(limit)
                .offset(offset)
                .options(
                    selectinload(ListingJobRow.images),
                    selectinload(ListingJobRow.generation_items),
                )
            )
            rows = list((await session.execute(stmt)).scalars().all())
        return [
            self._summary_of(r)
            for r in rows
        ]

    @staticmethod
    def _summary_of(r: ListingJobRow) -> ListingJobSummary:
        # 失败张也落库（两阶段 ISSUE-0047）：缩略图/计数只算成功张，保 image_count 旧语义
        # （历史上仅成功张入库，前端据此展缩略、失败张空 image_key 不可展）。按 id 稳序取首成功。
        successes = sorted(
            (im for im in r.images if im.status == "成功"), key=lambda im: im.id
        )
        available = [
            image
            for image in successes
            if image.moderation_status == "normal"
        ]
        return ListingJobSummary(
            job_id=r.id,
            status=r.status,
            platform=r.platform,
            ratio=r.ratio,
            n=r.n,
            total_cost=r.total_cost,
            created_at=r.created_at,
            first_image_key=(available[0].image_key if available else None),
            image_count=len(successes),
            edit_mode=r.edit_mode,
            category=r.category,
            operation_type=SqlAlchemyListingHistoryQuery._operation_type_of(r),
        )

    async def get_job(self, *, job_id: str, user_id: str) -> ListingJobDetail | None:
        async with self._session_factory() as session:
            stmt = (
                select(ListingJobRow)
                .where(ListingJobRow.id == job_id, ListingJobRow.user_id == user_id)
                .options(
                    selectinload(ListingJobRow.images),
                    selectinload(ListingJobRow.inputs),
                    selectinload(ListingJobRow.generation_items),
                )
            )
            row = (await session.execute(stmt)).scalar_one_or_none()
            if row is None:
                return None
            source_image_type: str | None = None
            source_image_available = False
            chain_cost: Decimal | None = None
            if row.edit_mode is not None:  # 编辑单：补源张图型 + 迭代链累计（R5 根计源张）
                src_stmt = (
                    select(
                        ListingImageRow.image_type,
                        ListingImageRow.moderation_status,
                    )
                    .where(
                        ListingImageRow.job_id == row.parent_job_id,
                        ListingImageRow.image_key == row.source_image_key,
                        ListingImageRow.status == "成功",
                    )
                    .order_by(desc(ListingImageRow.id))
                    .limit(1)
                )
                source = (await session.execute(src_stmt)).one_or_none()
                if source is not None:
                    source_image_type = source[0]
                    source_image_available = source[1] == "normal"
                chain_cost = await self._chain_cost(session, row)
        inputs = sorted(row.inputs, key=lambda i: i.ord)
        return ListingJobDetail(
            job_id=row.id,
            prompt=row.prompt,
            modifiers={str(k): str(v) for k, v in row.modifiers.items()},
            platform=row.platform,
            ratio=row.ratio,
            size=row.size,
            n=row.n,
            status=row.status,
            total_cost=row.total_cost,
            error=row.error,
            created_at=row.created_at,
            completed_at=row.completed_at,
            category=row.category,
            images=tuple(
                ListingJobImageView(
                    image_key=im.image_key, seed=im.seed, cost=im.cost,
                    status=im.status,
                    available=(
                        im.status == "成功"
                        and im.moderation_status == "normal"
                    ),
                    image_type=im.image_type,
                )
                for im in row.images
            ),
            input_keys=tuple(i.upload_key for i in inputs),
            clone_mode=row.clone_mode,
            input_roles=tuple(i.role for i in inputs),
            parent_job_id=row.parent_job_id,
            edit_mode=row.edit_mode,
            source_image_key=row.source_image_key,
            source_image_available=source_image_available,
            source_image_type=source_image_type,
            chain_cost=chain_cost,
            operation_type=self._operation_type_of(row),
        )

    @staticmethod
    def _operation_type_of(row: ListingJobRow) -> str | None:
        if not row.generation_items:
            return None
        operation_types = {
            item.operation_type for item in row.generation_items
        }
        if len(operation_types) != 1:
            raise RuntimeError(
                f"任务 {row.id} 包含不一致的操作类型（数据异常）"
            )
        return operation_types.pop()

    async def _chain_cost(self, session: AsyncSession, row: ListingJobRow) -> Decimal:
        """迭代链累计（R5）：路径上各编辑单 total_cost + 根单被编辑「源张」单张 cost。

        根计源张不计整单（根是 5 张套图时算 ¥0.40 不算整套）；读时沿链 O(深度)
        计算、不落库（零迁移）。祖先 owner 写路径已强制同人，读路径防御性核、
        异常即停止聚合（如实少算、不假造）。
        """
        total = Decimal("0")
        cur = row
        seen = {cur.id}  # 环不可能（parent 服务端生成=DAG），防御性护栏
        while True:
            total += cur.total_cost  # cur 必为编辑单（入口 row.edit_mode 非 None）
            parent = await session.get(ListingJobRow, cur.parent_job_id)
            if parent is None or parent.user_id != cur.user_id or parent.id in seen:
                break
            if parent.edit_mode is not None:
                seen.add(parent.id)
                cur = parent
                continue
            # parent=链根（非编辑单）：加被编辑源张的单张 cost，链终
            src_stmt = (
                select(ListingImageRow.cost)
                .where(
                    ListingImageRow.job_id == parent.id,
                    ListingImageRow.image_key == cur.source_image_key,
                )
                .order_by(desc(ListingImageRow.id))
                .limit(1)
            )
            src_cost = (await session.execute(src_stmt)).scalar_one_or_none()
            if src_cost is not None:
                total += src_cost
            break
        return total

    async def resolve_generated_image_source(
        self, *, source_image_key: str, user_id: str
    ) -> GeneratedImageSource | None:
        async with self._session_factory() as session:
            # 一条谓词同时完成：owner 过滤（D1 第一核）/失败张排除（Q-δ）/内容寻址多行收敛
            stmt = (
                select(ListingJobRow)
                .join(ListingImageRow, ListingImageRow.job_id == ListingJobRow.id)
                .where(
                    ListingImageRow.image_key == source_image_key,
                    ListingJobRow.user_id == user_id,
                    ListingImageRow.status == "成功",
                    ListingImageRow.moderation_status == "normal",
                )
                .order_by(desc(ListingImageRow.created_at), desc(ListingImageRow.id))
                .limit(1)
            )
            parent = (await session.execute(stmt)).scalar_one_or_none()
            if parent is None:
                return None
            root = parent
            seen = {root.id}  # 环不可能（DAG），防御性护栏
            while root.parent_job_id is not None:
                nxt = await session.get(ListingJobRow, root.parent_job_id)
                # 链断/越权/异常 → 404 同口径（D1 第二核：顺路核每跳 owner）
                if nxt is None or nxt.user_id != user_id or nxt.id in seen:
                    return None
                seen.add(nxt.id)
                root = nxt
            in_stmt = (
                select(ListingJobInputRow)
                .where(
                    ListingJobInputRow.job_id == root.id,
                    # 链根产品锚：clone 根 role='product'（恰 1）；generate/套图根 role 全
                    # NULL（1..3 全是产品图）——一条谓词统一两类根（Q-δ 通路一致性）
                    or_(
                        ListingJobInputRow.role == "product",
                        ListingJobInputRow.role.is_(None),
                    ),
                )
                .order_by(ListingJobInputRow.ord)
            )
            anchors = list((await session.execute(in_stmt)).scalars().all())
        if not anchors:
            # 不可能态：根 job 必有产品输入（历史写入强制）；缺=数据异常，fail-fast 500
            raise RuntimeError(f"链根 {root.id} 无产品输入（数据异常）")
        return GeneratedImageSource(
            parent_job_id=parent.id,
            parent_ratio=parent.ratio,
            parent_modifiers={str(k): str(v) for k, v in parent.modifiers.items()},
            root_product_upload_keys=tuple(a.upload_key for a in anchors),
        )
