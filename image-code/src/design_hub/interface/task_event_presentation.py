from collections.abc import Mapping

from design_hub.domain.enums import TaskEventType
from design_hub.domain.errors import DataInvariantError
from design_hub.ports.media_url_signer import MediaUrlSigner


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
