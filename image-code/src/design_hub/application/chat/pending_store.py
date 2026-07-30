"""待确认出图动作的内存态（confirm_token 过程态，取舍⑤不落库；ISSUE-0051）。

对话转录已迁 DB（ChatSessionRepository）；本模块只留 confirm_token 这一过程态，按 session_id 键。
一次性 + 绑 session + TTL（#884①④）。服务重启即失=可接受（过程态）。
"""

import secrets
import time
from dataclasses import dataclass, field
from decimal import Decimal

from design_hub.application.listing.requests import (
    BackgroundReplaceRequest,
    CloneRequest,
    EditRequest,
    ListingGenerateRequest,
)
from design_hub.domain.tasking import RenderTier

ListingReq = (
    ListingGenerateRequest
    | CloneRequest
    | EditRequest
    | BackgroundReplaceRequest
)


@dataclass
class PendingAction:
    """待用户确认的出图动作（费用闸暂停态）。"""

    confirm_token: str
    tool: str  # generate | clone | edit | replace_background
    req: ListingReq
    count: int
    estimate: Decimal
    model: str
    render_tier: RenderTier
    expires_at: float  # time.monotonic() 基准


@dataclass
class PendingStore:
    """session_id → PendingAction 内存态。"""

    ttl_seconds: float = 600.0  # confirm_token TTL 10min（#884①）
    _pending: dict[str, PendingAction] = field(default_factory=dict)

    def new(
        self,
        session_id: str,
        *,
        tool: str,
        req: ListingReq,
        count: int,
        estimate: Decimal,
        model: str,
        render_tier: RenderTier,
    ) -> PendingAction:
        pending = PendingAction(
            confirm_token="ct_" + secrets.token_urlsafe(16),
            tool=tool,
            req=req,
            count=count,
            estimate=estimate,
            model=model,
            render_tier=render_tier,
            expires_at=time.monotonic() + self.ttl_seconds,
        )
        self._pending[session_id] = pending
        return pending

    def take(self, session_id: str, confirm_token: str) -> PendingAction | None:
        """匹配即消费（一次性）。None = 无 pending / token 不匹配 / 已过期。"""
        pending = self._pending.get(session_id)
        if pending is None or pending.confirm_token != confirm_token:
            return None  # 不匹配：不动用户的有效 pending（防他人作废）
        del self._pending[session_id]  # 匹配 → 消费（一次性，无论是否过期）
        if time.monotonic() > pending.expires_at:
            return None
        return pending

    def clear(self, session_id: str) -> None:
        self._pending.pop(session_id, None)  # 新消息作废旧 pending / cancel 立即作废
