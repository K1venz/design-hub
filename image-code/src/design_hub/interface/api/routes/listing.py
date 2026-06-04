import json
import uuid
from collections.abc import AsyncIterator
from typing import Annotated

from fastapi import APIRouter, Form, Header, Request, UploadFile
from fastapi.responses import StreamingResponse

from design_hub.application.listing.commands import ListingGenerationCommand
from design_hub.application.listing.listing_service import ListingGenerationService
from design_hub.domain.errors import DomainError
from design_hub.domain.models import TaskEvent
from design_hub.interface.api.deps import CurrentUserDep, CurrentUserSseDep
from design_hub.ports.events import EventPublisher, EventStream
from design_hub.ports.listing_history import ListingHistory
from design_hub.ports.task_queue import TaskQueue

router = APIRouter(prefix="/listing", tags=["listing"])


def _sse(event: TaskEvent) -> str:
    return f"event: {event.type.value}\ndata: {json.dumps(event.data, ensure_ascii=False)}\n\n"


@router.post("/generate")
async def generate_listing(
    request: Request,
    _user: CurrentUserDep,  # 需 Bearer
    images: list[UploadFile],
    prompt: Annotated[str, Form()],
    ratio: Annotated[str, Form()],
    n: Annotated[int, Form()],
    modifiers: Annotated[str, Form()] = "{}",
    user_id: Annotated[str, Header(alias="X-User-Id")] = "designer-anon",
) -> dict[str, str]:
    """listing 一键出图：multipart 直传 ≤3 图 + prompt + modifiers，异步返回 job_id。"""
    if not 1 <= len(images) <= 3:
        raise DomainError(f"图片数量需为 1..3，实际 {len(images)}")
    parsed = json.loads(modifiers)  # 非法 JSON → ValueError → 400
    if not isinstance(parsed, dict):
        raise DomainError("modifiers 必须是 JSON 对象")
    image_bytes = tuple([await f.read() for f in images])
    queue: TaskQueue = request.app.state.task_queue
    service: ListingGenerationService = request.app.state.listing_service
    history: ListingHistory = request.app.state.listing_history
    events: EventPublisher = request.app.state.event_stream
    job_id = uuid.uuid4().hex
    command = ListingGenerationCommand(
        service=service,
        events=events,
        history=history,
        user_id=user_id,
        prompt=prompt,
        modifiers={str(k): str(v) for k, v in parsed.items()},
        images=image_bytes,
        ratio=ratio,
        n=n,
    )
    await queue.enqueue(job_id=job_id, command=command)
    return {"job_id": job_id}


@router.get("/{job_id}/events")
async def listing_events(
    job_id: str, request: Request, _user: CurrentUserSseDep
) -> StreamingResponse:
    # SSE 鉴权经 ?access_token=（原生 EventSource 不能带头，ISSUE-0011）
    stream: EventStream = request.app.state.event_stream

    async def generator() -> AsyncIterator[str]:
        async for event in stream.subscribe(job_id):
            yield _sse(event)

    return StreamingResponse(generator(), media_type="text/event-stream")
