import asyncio
import json
from collections.abc import AsyncIterator

from fastapi import APIRouter, Request
from fastapi.responses import StreamingResponse

from design_hub.application.chat.orchestrator import ChatEvent, ChatOrchestrator
from design_hub.domain.enums import TaskEventType
from design_hub.domain.errors import DataInvariantError, NotFoundError
from design_hub.interface.api.deps import CurrentUserDep
from design_hub.interface.chat_schemas import (
    ChatConfirmRequest,
    ChatMessageRequest,
    ChatSessionSummaryOut,
    ChatTranscriptOut,
)
from design_hub.interface.task_event_presentation import (
    SSE_RESPONSE_HEADERS,
    log_sse_image_emitted,
    present_task_event_data,
)
from design_hub.ports.chat_repository import ChatSessionRepository
from design_hub.ports.media_url_signer import MediaUrlSigner

router = APIRouter(prefix="/chat", tags=["chat"])
_CHAT_HEARTBEAT_SECONDS = 20.0


def _orchestrator(request: Request) -> ChatOrchestrator:
    orch = request.app.state.chat_orchestrator
    assert isinstance(orch, ChatOrchestrator)
    return orch


def _chat_repo(request: Request) -> ChatSessionRepository:
    repo = request.app.state.chat_repo
    assert isinstance(repo, ChatSessionRepository)
    return repo


def _sse(event: ChatEvent) -> str:
    return f"event: {event.type}\ndata: {json.dumps(event.data, ensure_ascii=False)}\n\n"


def _present_chat_event(
    event: ChatEvent,
    signer: MediaUrlSigner,
) -> ChatEvent:
    if event.type != "job_event":
        return event
    job_id = event.data.get("job_id")
    redis_id = event.data.get("redis_id")
    event_type_raw = event.data.get("type")
    inner_data = event.data.get("data")
    if not isinstance(job_id, str) or not job_id:
        raise DataInvariantError("chat job event job_id must be a non-empty string")
    if not isinstance(redis_id, str) or not redis_id:
        raise DataInvariantError("chat job event redis_id must be a non-empty string")
    if not isinstance(event_type_raw, str):
        raise DataInvariantError("chat job event type must be a string")
    if not isinstance(inner_data, dict):
        raise DataInvariantError("chat job event data must be an object")
    try:
        event_type = TaskEventType(event_type_raw)
    except ValueError as exc:
        raise DataInvariantError(
            f"unsupported chat job event type: {event_type_raw}"
        ) from exc
    presented = present_task_event_data(event_type, inner_data, signer)
    if event_type == TaskEventType.IMAGE_GENERATED:
        item_id = presented["item_id"]
        assert isinstance(item_id, str)
        log_sse_image_emitted(
            job_id=job_id,
            item_id=item_id,
            redis_id=redis_id,
            endpoint_kind="chat",
        )
    return ChatEvent(event.type, {**event.data, "data": presented})


async def _next_chat_event(iterator: AsyncIterator[ChatEvent]) -> ChatEvent:
    return await iterator.__anext__()


async def _stream_chat_events(
    events: AsyncIterator[ChatEvent],
    signer: MediaUrlSigner,
    *,
    heartbeat_seconds: float = _CHAT_HEARTBEAT_SECONDS,
) -> AsyncIterator[str]:
    """Keep the upstream iterator alive while emitting proxy-safe SSE comments."""
    iterator = aiter(events)
    pending: asyncio.Task[ChatEvent] | None = None
    try:
        while True:
            if pending is None:
                pending = asyncio.create_task(_next_chat_event(iterator))
            done, _ = await asyncio.wait({pending}, timeout=heartbeat_seconds)
            if not done:
                yield ": keep-alive\n\n"
                continue
            try:
                event = pending.result()
            except StopAsyncIteration:
                pending = None
                return
            pending = None
            yield _sse(_present_chat_event(event, signer))
    finally:
        if pending is not None and not pending.done():
            pending.cancel()
            try:
                await pending
            except asyncio.CancelledError:
                pass
        close = getattr(iterator, "aclose", None)
        if close is not None:
            await close()


@router.post("/messages")
async def chat_messages(
    req: ChatMessageRequest, request: Request, user: CurrentUserDep
) -> StreamingResponse:
    """发一句话，流式收一轮（帮我设计 Agent 对话入口，方案 C）。Bearer 头鉴权。

    事件序：session → assistant_delta* → [step → tool_call → generation_confirm] → assistant_end。
    触发出图时等待 generation_confirm 的显式用户动作。
    """
    orch = _orchestrator(request)

    events = orch.handle_message(
        user,
        req.session_id,
        req.message,
        req.upload_ids,
        chat_model=req.chat_model,
        image_model=req.image_model,
        image_options=req.image_options.to_application(),
        edit_source_image_key=req.edit_source_image_key,
    )
    signer: MediaUrlSigner = request.app.state.media_signer
    return StreamingResponse(
        _stream_chat_events(events, signer),
        media_type="text/event-stream",
        headers=SSE_RESPONSE_HEADERS,
    )


@router.post("/confirm")
async def chat_confirm(
    req: ChatConfirmRequest, request: Request, user: CurrentUserDep
) -> StreamingResponse:
    """生成确认动作。confirm→启 job 流式回传 job_event；cancel→作废 token。"""
    orch = _orchestrator(request)

    events = orch.handle_confirm(
        user, req.session_id, req.confirm_token, req.action
    )
    signer: MediaUrlSigner = request.app.state.media_signer
    return StreamingResponse(
        _stream_chat_events(events, signer),
        media_type="text/event-stream",
        headers=SSE_RESPONSE_HEADERS,
    )


# ── 对话历史回显（ISSUE-0051）：复用 Bearer 鉴权 + owner 隔离（越权 404 anti-enum）──


@router.get("/sessions")
async def list_sessions(request: Request, user: CurrentUserDep) -> list[ChatSessionSummaryOut]:
    """我的会话列表（侧栏，updated_at 倒序、带消息数）。"""
    summaries = await _chat_repo(request).list_sessions(user.user_id)
    return [ChatSessionSummaryOut.of(s) for s in summaries]


@router.get("/sessions/{session_id}")
async def get_session(
    session_id: str, request: Request, user: CurrentUserDep
) -> ChatTranscriptOut:
    """完整转录回显（非本人 / 不存在 → 404 anti-enum）。job_id 消息前端 useListingJob 现签取图。"""
    transcript = await _chat_repo(request).get_transcript(session_id, user.user_id)
    if transcript is None:
        raise NotFoundError(f"会话不存在或无权访问：{session_id}")
    return ChatTranscriptOut.of(transcript)


@router.delete("/sessions/{session_id}")
async def delete_session(
    session_id: str, request: Request, user: CurrentUserDep
) -> dict[str, bool]:
    """硬删会话（CASCADE 删消息）；非本人 / 不存在 → 404。"""
    if not await _chat_repo(request).delete_session(session_id, user.user_id):
        raise NotFoundError(f"会话不存在或无权访问：{session_id}")
    return {"ok": True}
