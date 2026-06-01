# 注解延迟求值：根除方法名遮蔽内置类型的隐患（参见 ISSUE-0004）
from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from design_hub.domain.enums import RevisionStatus
from design_hub.domain.errors import NotFoundError
from design_hub.domain.models import RevisionItem, RevisionRecord
from design_hub.infrastructure.db.models import Revision
from design_hub.ports.revision_repository import RevisionRepository


def _to_record(row: Revision) -> RevisionRecord:
    items = tuple(
        RevisionItem(
            seq=int(it["seq"]),
            text=str(it["text"]),
            done=bool(it.get("done", False)),
            related_image_id=it.get("related_image_id"),
        )
        for it in row.items
    )
    return RevisionRecord(
        id=row.id,
        project_id=row.project_id,
        round_no=row.round_no,
        items=items,
        status=RevisionStatus(row.status),
        deadline=row.deadline,
    )


def _derive_status(items: list[dict[str, Any]]) -> str:
    all_done = bool(items) and all(bool(i.get("done", False)) for i in items)
    return (RevisionStatus.DONE if all_done else RevisionStatus.OPEN).value


class SqlAlchemyRevisionRepository(RevisionRepository):
    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._session_factory = session_factory

    async def create(
        self, *, project_id: int, round_no: int, deadline: datetime | None = None
    ) -> RevisionRecord:
        async with self._session_factory() as session:
            row = Revision(
                project_id=project_id,
                round_no=round_no,
                items=[],
                status=RevisionStatus.OPEN.value,
                deadline=deadline,
            )
            session.add(row)
            await session.commit()
            await session.refresh(row)
            return _to_record(row)

    async def get(self, revision_id: int) -> RevisionRecord | None:
        async with self._session_factory() as session:
            row = await session.get(Revision, revision_id)
            return _to_record(row) if row is not None else None

    async def list_by_project(self, project_id: int) -> list[RevisionRecord]:
        async with self._session_factory() as session:
            stmt = select(Revision).where(Revision.project_id == project_id).order_by(Revision.id)
            rows = (await session.execute(stmt)).scalars().all()
            return [_to_record(r) for r in rows]

    async def add_item(
        self, revision_id: int, *, text: str, related_image_id: int | None = None
    ) -> RevisionRecord:
        async with self._session_factory() as session:
            row = await session.get(Revision, revision_id)
            if row is None:
                raise NotFoundError(f"改稿单 {revision_id} 不存在")
            items: list[dict[str, Any]] = [dict(i) for i in row.items]
            next_seq = max((int(i["seq"]) for i in items), default=0) + 1
            items.append(
                {"seq": next_seq, "text": text, "done": False, "related_image_id": related_image_id}
            )
            row.items = items  # 整体重赋值：触发 JSON 列脏检测（in-place append 不会）
            row.status = _derive_status(items)
            await session.commit()
            await session.refresh(row)
            return _to_record(row)

    async def set_item_done(self, revision_id: int, seq: int, *, done: bool) -> RevisionRecord:
        async with self._session_factory() as session:
            row = await session.get(Revision, revision_id)
            if row is None:
                raise NotFoundError(f"改稿单 {revision_id} 不存在")
            items: list[dict[str, Any]] = [dict(i) for i in row.items]
            target = next((i for i in items if int(i["seq"]) == seq), None)
            if target is None:
                raise NotFoundError(f"改稿单 {revision_id} 无条目 {seq}")
            target["done"] = done
            row.items = items
            row.status = _derive_status(items)
            await session.commit()
            await session.refresh(row)
            return _to_record(row)

    async def has_open_items(self, project_id: int) -> bool:
        async with self._session_factory() as session:
            stmt = select(Revision).where(Revision.project_id == project_id)
            rows = (await session.execute(stmt)).scalars().all()
            return any(not bool(it.get("done", False)) for row in rows for it in row.items)
