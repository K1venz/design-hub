"""对话会话内存态（MVP 不落库，避 DB 签字；单进程 dict，刷新/重启即失，对齐 spec §四）。

owner 隔离：get 以 (session_id, user_id) 取，非本人当作不存在（防跨用户会话）。
confirm_token：一次性 + 绑 session + TTL（#884①④）。确需持久化=STOP。
"""

import secrets
import time
from dataclasses import dataclass, field
from decimal import Decimal

from design_hub.application.listing.requests import (
    CloneRequest,
    EditRequest,
    ListingGenerateRequest,
)
from design_hub.ports.text_llm import ChatMessage

ListingReq = ListingGenerateRequest | CloneRequest | EditRequest


@dataclass
class PendingAction:
    """待用户确认的出图动作（费用闸暂停态）。"""

    confirm_token: str
    tool: str  # generate | clone | edit
    req: ListingReq
    count: int
    estimate: Decimal
    expires_at: float  # time.monotonic() 基准
    tool_call_id: str = ""  # 原始 LLM tool_call id（收尾轮 tool 消息回链用）


@dataclass
class ChatSession:
    session_id: str
    user_id: str
    messages: list[ChatMessage] = field(default_factory=list)
    job_count: int = 0  # 会话级出图单数（闸用，#884②）
    pending: PendingAction | None = None


@dataclass
class InMemorySessionStore:
    ttl_seconds: float = 600.0  # confirm_token TTL 10min（#884①）
    _sessions: dict[str, ChatSession] = field(default_factory=dict)

    def create(self, user_id: str) -> ChatSession:
        sid = secrets.token_urlsafe(12)
        session = ChatSession(session_id=sid, user_id=user_id)
        self._sessions[sid] = session
        return session

    def get(self, session_id: str, user_id: str) -> ChatSession | None:
        session = self._sessions.get(session_id)
        if session is None or session.user_id != user_id:  # owner 隔离
            return None
        return session

    def new_pending(
        self,
        session: ChatSession,
        *,
        tool: str,
        req: ListingReq,
        count: int,
        estimate: Decimal,
        tool_call_id: str = "",
    ) -> PendingAction:
        pending = PendingAction(
            confirm_token="ct_" + secrets.token_urlsafe(16),
            tool=tool,
            req=req,
            count=count,
            estimate=estimate,
            expires_at=time.monotonic() + self.ttl_seconds,
            tool_call_id=tool_call_id,
        )
        session.pending = pending
        return pending

    def take_pending(self, session: ChatSession, confirm_token: str) -> PendingAction | None:
        """匹配即消费（一次性）。None = 无 pending / token 不匹配 / 已过期。"""
        pending = session.pending
        if pending is None or pending.confirm_token != confirm_token:
            return None  # 不匹配：不动用户的有效 pending（防他人作废）
        session.pending = None  # 匹配 → 消费（一次性，无论是否过期）
        if time.monotonic() > pending.expires_at:
            return None
        return pending

    def cancel_pending(self, session: ChatSession) -> None:
        session.pending = None  # cancel 立即作废 token（#884④）
