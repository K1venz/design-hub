from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Query
from starlette.concurrency import run_in_threadpool

from design_hub.domain.runtime_logs import (
    RuntimeLogLevel,
    RuntimeLogQuery,
    RuntimeLogServiceName,
)
from design_hub.interface.admin_console_schemas import (
    RuntimeLogDetailOut,
    RuntimeLogPageOut,
)
from design_hub.interface.api.deps import (
    CurrentManagerDep,
    RuntimeLogServiceDep,
)

router = APIRouter(prefix="/admin/runtime-logs", tags=["admin"])


@router.get("", response_model=RuntimeLogPageOut)
async def list_runtime_logs(
    manager: CurrentManagerDep,
    service: RuntimeLogServiceDep,
    level: RuntimeLogLevel | None = None,
    source: Annotated[
        RuntimeLogServiceName | None,
        Query(alias="service"),
    ] = None,
    chain: str | None = None,
    trace_id: str | None = None,
    job_id: str | None = None,
    start: datetime | None = None,
    end: datetime | None = None,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> RuntimeLogPageOut:
    del manager
    page = await run_in_threadpool(
        service.list,
        RuntimeLogQuery(
            level=level,
            service=source,
            chain=chain,
            trace_id=trace_id,
            job_id=job_id,
            start=start,
            end=end,
        ),
        limit=limit,
        offset=offset,
    )
    return RuntimeLogPageOut.of(page)


@router.get("/{event_id}", response_model=RuntimeLogDetailOut)
async def get_runtime_log(
    event_id: str,
    manager: CurrentManagerDep,
    service: RuntimeLogServiceDep,
) -> RuntimeLogDetailOut:
    del manager
    entry = await run_in_threadpool(service.get, event_id)
    return RuntimeLogDetailOut.of(entry)


@router.get(
    "/{event_id}/trace",
    response_model=list[RuntimeLogDetailOut],
)
async def get_runtime_log_trace(
    event_id: str,
    manager: CurrentManagerDep,
    service: RuntimeLogServiceDep,
) -> list[RuntimeLogDetailOut]:
    del manager
    entries = await run_in_threadpool(service.trace, event_id)
    return [RuntimeLogDetailOut.of(entry) for entry in entries]
