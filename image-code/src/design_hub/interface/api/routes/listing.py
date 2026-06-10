import json
import uuid
from collections.abc import AsyncIterator

from fastapi import APIRouter, Request
from fastapi.responses import StreamingResponse

from design_hub.application.listing.commands import CloneCommand, ListingGenerationCommand
from design_hub.application.listing.listing_service import (
    ListingGenerationService,
    build_listing_prompts,
)
from design_hub.application.listing.prompt_composer import compose_clone_prompt
from design_hub.application.listing.sizing import ratio_to_size
from design_hub.application.listing.upload_service import UploadService
from design_hub.domain.errors import NotFoundError
from design_hub.domain.models import TaskEvent
from design_hub.interface.api.deps import CurrentUserDep, CurrentUserSseDep
from design_hub.interface.listing_history_schemas import (
    ListingJobDetailOut,
    ListingJobSummaryOut,
)
from design_hub.interface.listing_schemas import CloneRequest, ListingGenerateRequest
from design_hub.ports.events import EventPublisher, EventStream
from design_hub.ports.listing_history import ListingHistory
from design_hub.ports.listing_query import ListingHistoryQuery
from design_hub.ports.media_url_signer import MediaUrlSigner
from design_hub.ports.task_queue import TaskQueue
from design_hub.ports.upload_store import owns

router = APIRouter(prefix="/listing", tags=["listing"])


def _sse(event: TaskEvent) -> str:
    return f"event: {event.type.value}\ndata: {json.dumps(event.data, ensure_ascii=False)}\n\n"


@router.post("/generate")
async def generate_listing(
    req: ListingGenerateRequest,
    request: Request,
    user: CurrentUserDep,  # Bearer；身份即落库/历史/成本的 user_id（不用可伪造的 X-User-Id）
) -> dict[str, str]:
    """listing 出图（单图 n / 套图 plan 互斥，PRD §3.12.14）：异步返回 job_id。"""
    service: ListingGenerationService = request.app.state.listing_service
    uploads: UploadService = request.app.state.upload_service
    # 边界 fail-fast（ISSUE-0024）：入队前同步校验完所有输入，任一非法 → 4xx，不入队。
    if not 1 <= len(req.upload_ids) <= 3:
        raise ValueError(f"upload_ids 数量需为 1..3，实际 {len(req.upload_ids)}")
    ratio_to_size(req.ratio)
    overlay = tuple(req.overlay_texts) if req.overlay_texts else ()
    # 互斥/枚举/范围/overlay/图型卡/品类/下拉 全部 fail-fast（与编排同一事实源）
    build_listing_prompts(
        req.prompt, req.modifiers, service.modifier_registry, service.card_registry,
        service.type_registry,
        category=req.category, n=req.n, plan=req.plan, overlay_texts=overlay,
    )
    for uid in req.upload_ids:
        # 非自有/不存在 upload → 404：防枚举、对齐 GET /uploads 与 get_job（ISSUE-0032）
        if not owns(uid, user.user_id):
            raise NotFoundError(f"upload 不存在或无权访问：{uid}")
    # 本人命名空间内：load() 对非法格式→400、缺文件→404
    images = tuple([(await uploads.load(uid))[0] for uid in req.upload_ids])
    events: EventPublisher = request.app.state.event_stream
    history: ListingHistory = request.app.state.listing_history
    queue: TaskQueue = request.app.state.task_queue
    job_id = uuid.uuid4().hex
    command = ListingGenerationCommand(
        service=service,
        events=events,
        history=history,
        user_id=user.user_id,
        prompt=req.prompt,
        modifiers=req.modifiers,
        images=images,
        upload_keys=tuple(req.upload_ids),
        ratio=req.ratio,
        n=req.n,
        plan=req.plan,
        overlay_texts=overlay,
        category=req.category,
    )
    await queue.enqueue(job_id=job_id, command=command)
    return {"job_id": job_id}


@router.post("/clone")
async def clone_listing(
    req: CloneRequest,
    request: Request,
    user: CurrentUserDep,
) -> dict[str, str]:
    """爆款图复刻（PRD §3.13）：产品图==1 + 爆款参考图 1..2，两档复刻，异步返回 job_id。"""
    service: ListingGenerationService = request.app.state.listing_service
    uploads: UploadService = request.app.state.upload_service
    # 边界 fail-fast（ISSUE-0024 口径）：入队前同步校验完所有输入。
    if len(req.product_upload_ids) != 1:
        raise ValueError(f"产品图需为 1 张，实际 {len(req.product_upload_ids)}")
    if not 1 <= len(req.reference_upload_ids) <= 2:
        raise ValueError(f"爆款参考图需为 1..2 张，实际 {len(req.reference_upload_ids)}")
    ratio_to_size(req.ratio)
    # 档位/品类/下拉 fail-fast（与编排同一组装函数；prompt 选填、空=合法）
    compose_clone_prompt(
        req.prompt, req.modifiers, service.modifier_registry,
        category=req.category, card_registry=service.card_registry,
        clone_registry=service.clone_registry, clone_mode=req.clone_mode,
    )
    ordered_ids = [*req.product_upload_ids, *req.reference_upload_ids]  # 产品前·参考后=角色契约
    for uid in ordered_ids:
        # 非自有/不存在 upload → 404：防枚举（ISSUE-0032/0041 血脉），双角色同口径
        if not owns(uid, user.user_id):
            raise NotFoundError(f"upload 不存在或无权访问：{uid}")
    loaded = [(await uploads.load(uid))[0] for uid in ordered_ids]
    events: EventPublisher = request.app.state.event_stream
    history: ListingHistory = request.app.state.listing_history
    queue: TaskQueue = request.app.state.task_queue
    job_id = uuid.uuid4().hex
    command = CloneCommand(
        service=service,
        events=events,
        history=history,
        user_id=user.user_id,
        prompt=req.prompt,
        modifiers=req.modifiers,
        product_image=loaded[0],
        reference_images=tuple(loaded[1:]),
        upload_keys=tuple(ordered_ids),
        ratio=req.ratio,
        category=req.category,
        clone_mode=req.clone_mode,
    )
    await queue.enqueue(job_id=job_id, command=command)
    return {"job_id": job_id}


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
    job_id: str, request: Request, _user: CurrentUserSseDep
) -> StreamingResponse:
    # SSE 鉴权经 ?access_token=（原生 EventSource 不能带头，ISSUE-0011）
    stream: EventStream = request.app.state.event_stream

    async def generator() -> AsyncIterator[str]:
        async for event in stream.subscribe(job_id):
            yield _sse(event)

    return StreamingResponse(generator(), media_type="text/event-stream")
