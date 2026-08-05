from datetime import datetime
from typing import Annotated, Literal

from pydantic import BaseModel, Field, StringConstraints, model_validator

from design_hub.application.chat.image_options import (
    ChatImageOptions,
    ChatRenderTier,
)
from design_hub.domain.models import (
    ChatMessageRecord,
    ChatSessionSummary,
    ChatTranscript,
)


class ChatImageOptionsRequest(BaseModel):
    render_tier: ChatRenderTier
    ratio: Literal[
        "auto",
        "1:1",
        "3:2",
        "2:3",
        "3:4",
        "4:3",
        "9:16",
        "16:9",
        "4:5",
        "5:4",
        "1:2",
        "2:1",
    ]
    count: int | None = Field(ge=1, le=7)

    @model_validator(mode="after")
    def validate_four_k(self) -> "ChatImageOptionsRequest":
        self.to_application()
        return self

    def to_application(self) -> ChatImageOptions:
        return ChatImageOptions(
            render_tier=self.render_tier,
            ratio=self.ratio,
            count=self.count,
        )


class ChatMessageRequest(BaseModel):
    """POST /chat/messages 入参。session_id 首轮传 null，服务端建会话经 session 事件回传。"""

    session_id: str | None = None
    message: str
    chat_model: Annotated[
        str,
        StringConstraints(strip_whitespace=True, min_length=1),
    ]
    image_model: Annotated[
        str,
        StringConstraints(strip_whitespace=True, min_length=1),
    ]
    image_options: ChatImageOptionsRequest
    upload_ids: list[str] = Field(default_factory=list)  # 来自现有 POST /uploads（带图路径）
    edit_source_image_key: str | None = None


class ChatConfirmRequest(BaseModel):
    """POST /chat/confirm 入参（生成确认的显式用户动作）。"""

    session_id: str
    confirm_token: str
    action: str = "confirm"  # confirm | cancel


# ── 对话历史回显（ISSUE-0051）──


class ChatSessionSummaryOut(BaseModel):
    """GET /chat/sessions 列表项（侧栏，updated_at 倒序）。"""

    id: str
    title: str
    updated_at: datetime
    message_count: int

    @classmethod
    def of(cls, s: ChatSessionSummary) -> "ChatSessionSummaryOut":
        return cls(id=s.id, title=s.title, updated_at=s.updated_at, message_count=s.message_count)


class ChatMessageOut(BaseModel):
    """回显消息。job_id 非空→前端 useListingJob(job_id) 现签取图（取舍②，后端不内联 URL）。"""

    seq: int
    role: str
    content: str
    job_id: str | None = None
    attachment_upload_ids: list[str] = Field(default_factory=list)

    @classmethod
    def of(cls, m: ChatMessageRecord) -> "ChatMessageOut":
        return cls(
            seq=m.seq, role=m.role, content=m.content, job_id=m.job_id,
            attachment_upload_ids=list(m.attachment_upload_ids),
        )


class ChatTranscriptOut(BaseModel):
    """GET /chat/sessions/{id} 完整转录回显。"""

    id: str
    title: str
    messages: list[ChatMessageOut]

    @classmethod
    def of(cls, t: ChatTranscript) -> "ChatTranscriptOut":
        return cls(id=t.id, title=t.title, messages=[ChatMessageOut.of(m) for m in t.messages])
