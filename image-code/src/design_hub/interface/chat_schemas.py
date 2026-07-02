from pydantic import BaseModel, Field


class ChatMessageRequest(BaseModel):
    """POST /chat/messages 入参。session_id 首轮传 null，服务端建会话经 session 事件回传。"""

    session_id: str | None = None
    message: str
    upload_ids: list[str] = Field(default_factory=list)  # 来自现有 POST /uploads（带图路径）


class ChatConfirmRequest(BaseModel):
    """POST /chat/confirm 入参（费用闸的显式用户动作）。"""

    session_id: str
    confirm_token: str
    action: str = "confirm"  # confirm | cancel
