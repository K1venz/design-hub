import json
import uuid
from collections.abc import AsyncIterator
from typing import Annotated

from fastapi import APIRouter, Header, Request
from fastapi.responses import StreamingResponse

from design_hub.application.listing.commands import ListingGenerationCommand
from design_hub.application.listing.listing_service import ListingGenerationService
from design_hub.application.listing.prompt_composer import compose_prompt
from design_hub.application.listing.sizing import ratio_to_size
from design_hub.application.listing.upload_service import UploadService
from design_hub.domain.models import TaskEvent
from design_hub.interface.api.deps import CurrentUserDep, CurrentUserSseDep
from design_hub.interface.listing_schemas import ListingGenerateRequest
from design_hub.ports.events import EventPublisher, EventStream
from design_hub.ports.listing_history import ListingHistory
from design_hub.ports.task_queue import TaskQueue

router = APIRouter(prefix="/listing", tags=["listing"])


def _sse(event: TaskEvent) -> str:
    return f"event: {event.type.value}\ndata: {json.dumps(event.data, ensure_ascii=False)}\n\n"


@router.post("/generate")
async def generate_listing(
    req: ListingGenerateRequest,
    request: Request,
    _user: CurrentUserDep,  # 需 Bearer
    user_id: Annotated[str, Header(alias="X-User-Id")] = "designer-anon",
) -> dict[str, str]:
    """listing 一键出图（两步流，ISSUE-0026）：入参经 upload_ids 引用已上传图，异步返回 job_id。"""
    service: ListingGenerationService = request.app.state.listing_service
    uploads: UploadService = request.app.state.upload_service
    # 边界 fail-fast（ISSUE-0024）：入队前同步校验完所有输入，任一非法 → 4xx，不入队、不发 job_id。
    # 输入错误统一 ValueError→400（区别于领域冲突 DomainError→409）。
    if not 1 <= len(req.upload_ids) <= 3:
        raise ValueError(f"upload_ids 数量需为 1..3，实际 {len(req.upload_ids)}")
    if not 1 <= req.n <= 7:
        raise ValueError(f"张数需为 1..7，实际 {req.n}")
    ratio_to_size(req.ratio)  # 非法比例 → ValueError(400)
    compose_prompt(req.prompt, req.modifiers, service.modifier_registry)  # 空 prompt/未知下拉 → 400
    # id 非法→400 / 不存在→404
    images = tuple([(await uploads.load(uid))[0] for uid in req.upload_ids])
    events: EventPublisher = request.app.state.event_stream
    history: ListingHistory = request.app.state.listing_history
    queue: TaskQueue = request.app.state.task_queue
    job_id = uuid.uuid4().hex
    command = ListingGenerationCommand(
        service=service,
        events=events,
        history=history,
        user_id=user_id,
        prompt=req.prompt,
        modifiers=req.modifiers,
        images=images,
        ratio=req.ratio,
        n=req.n,
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
