import json
from collections.abc import AsyncIterator

from fastapi import APIRouter, Request
from fastapi.responses import StreamingResponse

from design_hub.application.chat.orchestrator import ChatEvent, ChatOrchestrator
from design_hub.interface.api.deps import CurrentUserDep
from design_hub.interface.chat_schemas import ChatConfirmRequest, ChatMessageRequest

router = APIRouter(prefix="/chat", tags=["chat"])


def _orchestrator(request: Request) -> ChatOrchestrator:
    orch = request.app.state.chat_orchestrator
    assert isinstance(orch, ChatOrchestrator)
    return orch


def _sse(event: ChatEvent) -> str:
    return f"event: {event.type}\ndata: {json.dumps(event.data, ensure_ascii=False)}\n\n"


@router.post("/messages")
async def chat_messages(
    req: ChatMessageRequest, request: Request, user: CurrentUserDep
) -> StreamingResponse:
    """发一句话，流式收一轮（帮我设计 Agent 对话入口，方案 C）。Bearer 头鉴权。

    事件序：session → assistant_delta* → [step → tool_call → cost_confirm] → assistant_end。
    触发出图时在 cost_confirm 暂停（不出图、不扣费），等用户 POST /chat/confirm。
    """
    orch = _orchestrator(request)

    async def generator() -> AsyncIterator[str]:
        async for event in orch.handle_message(
            user, req.session_id, req.message, req.upload_ids
        ):
            yield _sse(event)

    return StreamingResponse(generator(), media_type="text/event-stream")


@router.post("/confirm")
async def chat_confirm(
    req: ChatConfirmRequest, request: Request, user: CurrentUserDep
) -> StreamingResponse:
    """费用确认的显式用户动作。confirm→启 job 流式回传 job_event；cancel→作废 token。"""
    orch = _orchestrator(request)

    async def generator() -> AsyncIterator[str]:
        async for event in orch.handle_confirm(
            user, req.session_id, req.confirm_token, req.action
        ):
            yield _sse(event)

    return StreamingResponse(generator(), media_type="text/event-stream")
