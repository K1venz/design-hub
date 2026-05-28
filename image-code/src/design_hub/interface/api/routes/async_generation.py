import json
import uuid
from collections.abc import AsyncIterator
from typing import Annotated

from fastapi import APIRouter, Depends, Header, Request
from fastapi.responses import StreamingResponse

from design_hub.domain.models import TaskEvent
from design_hub.interface.schemas import GenerateRequest
from design_hub.ports.events import EventStream
from design_hub.ports.task_queue import TaskQueue


def get_task_queue(request: Request) -> TaskQueue:
    queue = request.app.state.task_queue
    assert isinstance(queue, TaskQueue)
    return queue


def get_event_stream(request: Request) -> EventStream:
    stream = request.app.state.event_stream
    assert isinstance(stream, EventStream)
    return stream


QueueDep = Annotated[TaskQueue, Depends(get_task_queue)]
StreamDep = Annotated[EventStream, Depends(get_event_stream)]
UserIdDep = Annotated[str, Header(alias="X-User-Id")]

router = APIRouter(prefix="/generate", tags=["generation-async"])


def _sse(event: TaskEvent) -> str:
    return f"event: {event.type.value}\ndata: {json.dumps(event.data, ensure_ascii=False)}\n\n"


@router.post("/async")
async def enqueue(
    req: GenerateRequest,
    queue: QueueDep,
    user_id: UserIdDep = "designer-anon",
) -> dict[str, str]:
    """入队即返回 job_id；进度经 SSE 查询。"""
    job_id = uuid.uuid4().hex
    await queue.enqueue(job_id=job_id, brief=req.to_brief(), user_id=user_id)
    return {"job_id": job_id}


@router.get("/{job_id}/events")
async def stream_events(job_id: str, stream: StreamDep) -> StreamingResponse:
    async def generator() -> AsyncIterator[str]:
        async for event in stream.subscribe(job_id):
            yield _sse(event)

    return StreamingResponse(generator(), media_type="text/event-stream")
