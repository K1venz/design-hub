import json
from collections.abc import AsyncIterator

from fastapi import APIRouter, Request
from fastapi.responses import StreamingResponse

from design_hub.application.listing.job_launcher import ListingJobLauncher
from design_hub.application.listing.requests import (
    CloneRequest,
    EditRequest,
    ListingGenerateRequest,
)
from design_hub.domain.errors import NotFoundError
from design_hub.domain.models import TaskEvent
from design_hub.interface.api.deps import CurrentUserDep, CurrentUserSseDep
from design_hub.interface.listing_history_schemas import (
    ListingJobDetailOut,
    ListingJobSummaryOut,
)
from design_hub.ports.events import EventStream
from design_hub.ports.listing_query import ListingHistoryQuery
from design_hub.ports.media_url_signer import MediaUrlSigner

router = APIRouter(prefix="/listing", tags=["listing"])


def _launcher(request: Request) -> ListingJobLauncher:
    launcher = request.app.state.job_launcher
    assert isinstance(launcher, ListingJobLauncher)
    return launcher


def _sse(event: TaskEvent) -> str:
    return f"event: {event.type.value}\ndata: {json.dumps(event.data, ensure_ascii=False)}\n\n"


@router.post("/generate")
async def generate_listing(
    req: ListingGenerateRequest,
    request: Request,
    user: CurrentUserDep,  # Bearer；身份即落库/历史/成本的 user_id（不用可伪造的 X-User-Id）
) -> dict[str, str]:
    """listing 出图（单图 n / 套图 plan 互斥，PRD §3.12.14）：异步返回 job_id。"""
    job_id = await _launcher(request).launch_generate(user, req)
    return {"job_id": job_id}


@router.post("/clone")
async def clone_listing(
    req: CloneRequest,
    request: Request,
    user: CurrentUserDep,
) -> dict[str, str]:
    """爆款图复刻（PRD §3.13）：产品图==1 + 爆款参考图 1..2，两档复刻，异步返回 job_id。"""
    job_id = await _launcher(request).launch_clone(user, req)
    return {"job_id": job_id}


@router.post("/edit")
async def edit_listing(
    req: EditRequest,
    request: Request,
    user: CurrentUserDep,
) -> dict[str, str]:
    """二次编辑（PRD §3.12.13/ISSUE-0040）：基于本人产出图迭代（delta 微调 / full 重做）。"""
    job_id = await _launcher(request).launch_edit(user, req)
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
