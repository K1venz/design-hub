"""对话历史持久化端口（ISSUE-0051）。

DB = 转录事实源（取舍①只存 user 消息 + assistant 最终答复 + job_id）；owner 隔离在此端口内
（越权他人会话 → None/False，路由映射 404 anti-enum）。过程态（confirm_token）不经本端口。
"""

from abc import ABC, abstractmethod

from design_hub.domain.models import (
    ChatSessionSummary,
    ChatTranscript,
)


class ChatSessionRepository(ABC):
    """会话转录仓储（DIP）：SQL 实现按 LSP 替换。"""

    @abstractmethod
    async def create_session(self, *, session_id: str, user_id: str, title: str) -> None:
        """建会话行（首条消息触发）。"""
        ...

    @abstractmethod
    async def append_message(
        self,
        *,
        session_id: str,
        role: str,
        content: str,
        job_id: str | None = None,
        attachment_upload_ids: tuple[str, ...] = (),
    ) -> str:
        """Append a transcript message and return its stable message id."""
        ...

    @abstractmethod
    async def update_assistant_message(
        self,
        *,
        session_id: str,
        message_id: str,
        content: str,
    ) -> None:
        """Update one assistant message without changing its seq or job id."""
        ...

    @abstractmethod
    async def list_sessions(self, user_id: str) -> list[ChatSessionSummary]:
        """列该用户会话（updated_at 倒序，带消息数）。"""
        ...

    @abstractmethod
    async def get_transcript(self, session_id: str, user_id: str) -> ChatTranscript | None:
        """完整转录（seq 升序）；非本人/不存在 → None（路由 404 anti-enum）。"""
        ...

    @abstractmethod
    async def delete_session(self, session_id: str, user_id: str) -> bool:
        """硬删会话（CASCADE 删消息）；非本人/不存在 → False（路由 404）。"""
        ...

    @abstractmethod
    async def session_owned(self, session_id: str, user_id: str) -> bool:
        """会话是否本人所有（append/confirm 前 owner 校验）。"""
        ...

    @abstractmethod
    async def job_count(self, session_id: str) -> int:
        """本会话已出图单数（会话级闸派生：count job_id 非空的消息）。"""
        ...
