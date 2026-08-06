import json
import re
from collections.abc import AsyncIterator
from typing import Annotated, cast
from uuid import uuid4

from fastapi import APIRouter, Header, Request, status
from fastapi.responses import StreamingResponse

from design_hub.application.listing.requests import (
    BackgroundReplaceRequest,
    CloneRequest,
    EditRequest,
    ListingGenerateRequest,
)
from design_hub.application.listing.submission_service import (
    ListingSubmissionService,
    SubmissionReceipt,
)
from design_hub.domain.enums import TaskEventType
from design_hub.domain.errors import NotFoundError
from design_hub.infrastructure.monitoring.task_metrics import task_metrics
from design_hub.interface.api.deps import CurrentUserDep, CurrentUserSseDep
from design_hub.interface.listing_history_schemas import (
    ListingJobDetailOut,
    ListingJobSummaryOut,
    ListingSubmissionOut,
)
from design_hub.interface.task_event_presentation import (
    SSE_RESPONSE_HEADERS,
    log_sse_image_emitted,
    present_task_event_data,
)
from design_hub.ports.events import ReplayableEvent, ReplayableEventStream
from design_hub.ports.listing_query import ListingHistoryQuery
from design_hub.ports.media_url_signer import MediaUrlSigner

router = APIRouter(prefix="/listing", tags=["listing"])
_REDIS_ID = re.compile(r"(?:0|\d+)-\d+")
_TERMINAL_EVENTS = {
    TaskEventType.TASK_COMPLETED,
    TaskEventType.TASK_FAILED,
}


def _submission_service(request: Request) -> ListingSubmissionService:
    return cast(ListingSubmissionService, request.app.state.listing_submission)


def _sse(delivery: ReplayableEvent, signer: MediaUrlSigner) -> str:
    event = delivery.event
    data = present_task_event_data(event.type, event.data, signer)
    if event.type == TaskEventType.IMAGE_GENERATED:
        item_id = data["item_id"]
        assert isinstance(item_id, str)
        log_sse_image_emitted(
            job_id=event.job_id,
            item_id=item_id,
            redis_id=delivery.redis_id,
            endpoint_kind="listing",
        )
    return (
        f"id: {delivery.redis_id}\n"
        f"event: {event.type.value}\n"
        f"data: {json.dumps(data, ensure_ascii=False)}\n\n"
    )


def _idempotency_key(value: str | None) -> str:
    if value is None:
        raise ValueError("Idempotency-Key header is required")
    return value


def _correlation_ids(request: Request) -> tuple[str, str]:
    request_id = getattr(request.state, "request_id", None)
    if not isinstance(request_id, str) or not request_id:
        request_id = uuid4().hex
    trace_id = getattr(request.state, "trace_id", None)
    if not isinstance(trace_id, str) or not trace_id:
        trace_id = request_id
    return trace_id, request_id


def _submission_out(receipt: SubmissionReceipt) -> ListingSubmissionOut:
    return ListingSubmissionOut(
        job_id=receipt.job_id,
        queue_state=receipt.queue_state,
        estimated_wait_seconds=receipt.estimated_wait_seconds,
    )


@router.post(
    "/generate",
    status_code=status.HTTP_202_ACCEPTED,
    response_model=ListingSubmissionOut,
)
async def generate_listing(
    req: ListingGenerateRequest,
    request: Request,
    user: CurrentUserDep,  # Bearer；身份即落库/历史/成本的 user_id（不用可伪造的 X-User-Id）
    idempotency_key: Annotated[
        str | None, Header(alias="Idempotency-Key")
    ] = None,
) -> ListingSubmissionOut:
    """listing 出图（单图 n / 套图 plan 互斥，PRD §3.12.14）：异步返回 job_id。"""
    trace_id, request_id = _correlation_ids(request)
    receipt = await _submission_service(request).submit_generate(
        user_id=user.user_id,
        request=req,
        idempotency_key=_idempotency_key(idempotency_key),
        trace_id=trace_id,
        request_id=request_id,
    )
    return _submission_out(receipt)


@router.post(
    "/clone",
    status_code=status.HTTP_202_ACCEPTED,
    response_model=ListingSubmissionOut,
)
async def clone_listing(
    req: CloneRequest,
    request: Request,
    user: CurrentUserDep,
    idempotency_key: Annotated[
        str | None, Header(alias="Idempotency-Key")
    ] = None,
) -> ListingSubmissionOut:
    """爆款图复刻（PRD §3.13）：产品图==1 + 爆款参考图 1..2，两档复刻，异步返回 job_id。"""
    trace_id, request_id = _correlation_ids(request)
    receipt = await _submission_service(request).submit_clone(
        user_id=user.user_id,
        request=req,
        idempotency_key=_idempotency_key(idempotency_key),
        trace_id=trace_id,
        request_id=request_id,
    )
    return _submission_out(receipt)


@router.post(
    "/edit",
    status_code=status.HTTP_202_ACCEPTED,
    response_model=ListingSubmissionOut,
)
async def edit_listing(
    req: EditRequest,
    request: Request,
    user: CurrentUserDep,
    idempotency_key: Annotated[
        str | None, Header(alias="Idempotency-Key")
    ] = None,
) -> ListingSubmissionOut:
    """二次编辑（PRD §3.12.13/ISSUE-0040）：基于本人产出图迭代（delta 微调 / full 重做）。"""
    trace_id, request_id = _correlation_ids(request)
    receipt = await _submission_service(request).submit_edit(
        user_id=user.user_id,
        request=req,
        idempotency_key=_idempotency_key(idempotency_key),
        trace_id=trace_id,
        request_id=request_id,
    )
    return _submission_out(receipt)


@router.post(
    "/background-replace",
    status_code=status.HTTP_202_ACCEPTED,
    response_model=ListingSubmissionOut,
)
async def replace_listing_background(
    req: BackgroundReplaceRequest,
    request: Request,
    user: CurrentUserDep,
    idempotency_key: Annotated[
        str | None, Header(alias="Idempotency-Key")
    ] = None,
) -> ListingSubmissionOut:
    trace_id, request_id = _correlation_ids(request)
    receipt = await _submission_service(request).submit_background_replace(
        user_id=user.user_id,
        request=req,
        idempotency_key=_idempotency_key(idempotency_key),
        trace_id=trace_id,
        request_id=request_id,
    )
    return _submission_out(receipt)


@router.get("/jobs")
async def list_jobs(
    request: Request,
    user: CurrentUserDep,
    limit: int = 20,
    offset: int = 0,
    q: str | None = None,
) -> list[ListingJobSummaryOut]:
    """当前用户的 listing 历史（时间倒序、分页）；q 非空按 prompt/platform 模糊搜本人任务。"""
    if not 1 <= limit <= 100:
        raise ValueError(f"limit 需为 1..100，实际 {limit}")
    if offset < 0:
        raise ValueError(f"offset 不能为负，实际 {offset}")
    query: ListingHistoryQuery = request.app.state.listing_query
    signer: MediaUrlSigner = request.app.state.media_signer
    keyword = q.strip() if q else None
    summaries = await query.list_jobs(
        user_id=user.user_id, limit=limit, offset=offset, q=keyword or None
    )
    return [ListingJobSummaryOut.of(s, signer) for s in summaries]


@router.get("/jobs/{job_id}")
async def get_job(
    job_id: str, request: Request, user: CurrentUserDep
) -> ListingJobDetailOut:
    """listing 任务详情（仅本人；非本人 / 不存在 → 404，不泄露存在性）。"""
    query: ListingHistoryQuery = request.app.state.listing_query
    signer: MediaUrlSigner = request.app.state.media_signer
    detail = await query.get_job(job_id=job_id, user_id=user.user_id)
    if detail is None:
        raise NotFoundError(f"listing 任务不存在或无权访问：{job_id}")
    return ListingJobDetailOut.of(detail, signer)


@router.get("/{job_id}/events")
async def listing_events(
    job_id: str,
    request: Request,
    user: CurrentUserSseDep,
    last_event_id: Annotated[
        str | None, Header(alias="Last-Event-ID")
    ] = None,
) -> StreamingResponse:
    # SSE 鉴权经 ?access_token=（原生 EventSource 不能带头，ISSUE-0011）
    query: ListingHistoryQuery = request.app.state.listing_query
    if await query.get_job(job_id=job_id, user_id=user.user_id) is None:
        raise NotFoundError(f"listing 任务不存在或无权访问：{job_id}")
    if last_event_id is not None and _REDIS_ID.fullmatch(last_event_id) is None:
        raise ValueError("Last-Event-ID is invalid")
    stream: ReplayableEventStream = request.app.state.event_stream
    signer: MediaUrlSigner = request.app.state.media_signer

    async def generator() -> AsyncIterator[str]:
        cursor = last_event_id or "0-0"
        task_metrics.sse_opened()
        try:
            while True:
                events = await stream.read(
                    job_id=job_id,
                    after_id=cursor,
                    block_ms=15_000,
                )
                if not events:
                    yield ": keep-alive\n\n"
                    continue
                for event in events:
                    cursor = event.redis_id
                    yield _sse(event, signer)
                    if event.event.type in _TERMINAL_EVENTS:
                        return
        finally:
            task_metrics.sse_closed()

    return StreamingResponse(
        generator(),
        media_type="text/event-stream",
        headers=SSE_RESPONSE_HEADERS,
    )
