import pytest

from design_hub.domain.enums import TaskEventType
from design_hub.domain.errors import DataInvariantError
from design_hub.interface.task_event_presentation import present_task_event_data
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
