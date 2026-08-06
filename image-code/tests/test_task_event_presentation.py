import logging

import pytest

from design_hub.domain.enums import TaskEventType
from design_hub.domain.errors import DataInvariantError
from design_hub.domain.models import TaskEvent
from design_hub.interface.api.routes.listing import _sse as listing_sse
from design_hub.interface.task_event_presentation import (
    SSE_RESPONSE_HEADERS,
    present_task_event_data,
)
from design_hub.ports.events import ReplayableEvent
from design_hub.ports.media_url_signer import MediaUrlSigner


class StubSigner(MediaUrlSigner):
    def generated_url(self, key: str) -> str:
        return f"https://img.test/{key}?signed=1"

    def upload_url(self, key: str) -> str:
        return f"https://upload.test/{key}?signed=1"


def test_image_generated_is_presented_without_mutating_durable_data() -> None:
    raw: dict[str, object] = {
        "item_id": "item-1",
        "image_key": "result.png",
        "image_type": "场景",
        "seed": 7,
    }

    presented = present_task_event_data(
        TaskEventType.IMAGE_GENERATED,
        raw,
        StubSigner(),
    )

    assert presented == {
        **raw,
        "url": "https://img.test/result.png?signed=1",
    }
    assert raw == {
        "item_id": "item-1",
        "image_key": "result.png",
        "image_type": "场景",
        "seed": 7,
    }


@pytest.mark.parametrize("field", ["item_id", "image_key"])
def test_image_generated_requires_non_empty_identity_fields(field: str) -> None:
    data: dict[str, object] = {
        "item_id": "item-1",
        "image_key": "result.png",
    }
    data[field] = ""

    with pytest.raises(DataInvariantError, match=field):
        present_task_event_data(
            TaskEventType.IMAGE_GENERATED,
            data,
            StubSigner(),
        )


def test_image_failed_requires_item_id_and_other_events_pass_through() -> None:
    failed = {"item_id": "item-1", "error": "生成失败"}

    assert present_task_event_data(
        TaskEventType.IMAGE_FAILED,
        failed,
        StubSigner(),
    ) == failed
    assert present_task_event_data(
        TaskEventType.TASK_COMPLETED,
        {"total_cost": "0.05"},
        StubSigner(),
    ) == {"total_cost": "0.05"}

    with pytest.raises(DataInvariantError, match="item_id"):
        present_task_event_data(
            TaskEventType.IMAGE_FAILED,
            {"item_id": "", "error": "生成失败"},
            StubSigner(),
        )


def test_listing_sse_presents_and_logs_an_image_event(
    caplog: pytest.LogCaptureFixture,
) -> None:
    delivery = ReplayableEvent(
        redis_id="10-0",
        event=TaskEvent(
            job_id="job-1",
            type=TaskEventType.IMAGE_GENERATED,
            data={"item_id": "item-1", "image_key": "result.png"},
        ),
    )

    with caplog.at_level(logging.INFO):
        payload = listing_sse(delivery, StubSigner())

    assert "id: 10-0" in payload
    assert '"image_key": "result.png"' in payload
    assert '"url": "https://img.test/result.png?signed=1"' in payload
    emitted = [
        record
        for record in caplog.records
        if record.getMessage() == "generation_sse_image_emitted"
    ]
    assert len(emitted) == 1
    assert emitted[0].job_id == "job-1"
    assert emitted[0].item_id == "item-1"
    assert emitted[0].redis_id == "10-0"
    assert emitted[0].endpoint_kind == "listing"


def test_sse_response_headers_disable_caching_and_proxy_buffering() -> None:
    assert SSE_RESPONSE_HEADERS == {
        "Cache-Control": "no-cache",
        "X-Accel-Buffering": "no",
    }
