"""ChatSessionRepository 的 SQLAlchemy 实现（ISSUE-0051）。session-per-op，owner 隔离在读写内。"""

import uuid
from datetime import UTC, datetime

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from design_hub.domain.models import (
    ChatMessageRecord,
    ChatSessionSummary,
    ChatTranscript,
)
from design_hub.infrastructure.db.models import ChatMessageRow, ChatSessionRow
from design_hub.ports.chat_repository import ChatSessionRepository


class SqlAlchemyChatSessionRepository(ChatSessionRepository):
    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._session_factory = session_factory

    async def create_session(self, *, session_id: str, user_id: str, title: str) -> None:
        async with self._session_factory() as session:
            session.add(ChatSessionRow(id=session_id, user_id=user_id, title=title))
            await session.commit()

    async def append_message(
        self,
        *,
        session_id: str,
        role: str,
        content: str,
        job_id: str | None = None,
        attachment_upload_ids: tuple[str, ...] = (),
    ) -> None:
        async with self._session_factory() as session:
            max_seq = await session.scalar(
                select(func.max(ChatMessageRow.seq)).where(ChatMessageRow.session_id == session_id)
            )
            session.add(
                ChatMessageRow(
                    id=uuid.uuid4().hex,
                    session_id=session_id,
                    seq=0 if max_seq is None else int(max_seq) + 1,
                    role=role,
                    content=content,
                    job_id=job_id,
                    attachment_upload_ids=list(attachment_upload_ids) or None,
                )
            )
            row = await session.get(ChatSessionRow, session_id)
            if row is not None:
                row.updated_at = datetime.now(UTC)  # bump 列表倒序（子表 INSERT 不自动触发本表）
            await session.commit()

    async def list_sessions(self, user_id: str) -> list[ChatSessionSummary]:
        async with self._session_factory() as session:
            stmt = (
                select(ChatSessionRow, func.count(ChatMessageRow.id))
                .outerjoin(ChatMessageRow, ChatMessageRow.session_id == ChatSessionRow.id)
                .where(ChatSessionRow.user_id == user_id)
                .group_by(ChatSessionRow.id)
                .order_by(ChatSessionRow.updated_at.desc())
            )
            rows = (await session.execute(stmt)).all()
            return [
                ChatSessionSummary(
                    id=s.id, title=s.title, updated_at=s.updated_at, message_count=int(count)
                )
                for s, count in rows
            ]

    async def get_transcript(self, session_id: str, user_id: str) -> ChatTranscript | None:
        async with self._session_factory() as session:
            row = await session.get(ChatSessionRow, session_id)
            if row is None or row.user_id != user_id:  # owner 隔离 → None（路由 404）
                return None
            messages = (
                await session.execute(
                    select(ChatMessageRow)
                    .where(ChatMessageRow.session_id == session_id)
                    .order_by(ChatMessageRow.seq)
                )
            ).scalars().all()
            return ChatTranscript(
                id=row.id,
                title=row.title,
                messages=tuple(
                    ChatMessageRecord(
                        seq=m.seq,
                        role=m.role,
                        content=m.content,
                        job_id=m.job_id,
                        attachment_upload_ids=tuple(m.attachment_upload_ids or ()),
                    )
                    for m in messages
                ),
            )

    async def delete_session(self, session_id: str, user_id: str) -> bool:
        async with self._session_factory() as session:
            row = await session.get(ChatSessionRow, session_id)
            if row is None or row.user_id != user_id:  # 非本人/不存在 → 404
                return False
            await session.delete(row)  # ORM cascade + DB ondelete CASCADE 删消息
            await session.commit()
            return True

    async def session_owned(self, session_id: str, user_id: str) -> bool:
        async with self._session_factory() as session:
            row = await session.get(ChatSessionRow, session_id)
            return row is not None and row.user_id == user_id

    async def job_count(self, session_id: str) -> int:
        async with self._session_factory() as session:
            count = await session.scalar(
                select(func.count(ChatMessageRow.id)).where(
                    ChatMessageRow.session_id == session_id,
                    ChatMessageRow.job_id.is_not(None),
                )
            )
            return int(count or 0)
