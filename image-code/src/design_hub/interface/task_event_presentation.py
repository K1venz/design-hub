import logging
from collections.abc import Mapping
from typing import Literal

from design_hub.domain.enums import TaskEventType
from design_hub.domain.errors import DataInvariantError
from design_hub.ports.media_url_signer import MediaUrlSigner

logger = logging.getLogger(__name__)

SSE_RESPONSE_HEADERS = {
    "Cache-Control": "no-cache",
    "X-Accel-Buffering": "no",
}


def _required_text(data: Mapping[str, object], field: str) -> str:
    value = data.get(field)
    if not isinstance(value, str) or not value:
        raise DataInvariantError(
            f"task event {field} must be a non-empty string"
        )
    return value


def present_task_event_data(
    event_type: TaskEventType,
    data: Mapping[str, object],
    signer: MediaUrlSigner,
) -> dict[str, object]:
    presented = dict(data)
    if event_type == TaskEventType.IMAGE_GENERATED:
        _required_text(data, "item_id")
        image_key = _required_text(data, "image_key")
        presented["url"] = signer.generated_url(image_key)
    elif event_type == TaskEventType.IMAGE_FAILED:
        _required_text(data, "item_id")
    return presented


def log_sse_image_emitted(
    *,
    job_id: str,
    item_id: str,
    redis_id: str,
    endpoint_kind: Literal["listing", "chat"],
) -> None:
    logger.info(
        "generation_sse_image_emitted",
        extra={
            "chain": "image_generation",
            "action": "发送图片实时事件",
            "status": "emitted",
            "job_id": job_id,
            "item_id": item_id,
            "redis_id": redis_id,
            "endpoint_kind": endpoint_kind,
        },
    )
