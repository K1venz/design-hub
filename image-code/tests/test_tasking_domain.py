from datetime import UTC, datetime
from decimal import Decimal
from itertools import pairwise

import pytest

from design_hub.domain.tasking import (
    GenerationItemSpec,
    GenerationItemStatus,
    InvalidTaskMessage,
    InvalidTaskTransition,
    OperationType,
    ReferenceSnapshot,
    ReferenceSource,
    RenderTier,
    TaskMessage,
    is_terminal,
    require_transition,
)


def test_task_message_roundtrips_only_routing_fields() -> None:
    message = TaskMessage(
        schema_version=1,
        message_id="msg-1",
        trace_id="trace-1",
        request_id="request-1",
        job_id="job-1",
        item_id="item-1",
        operation_id="operation-1",
        operation_type=OperationType.GENERATE_IMAGE,
        user_id="user-1",
        created_at=datetime(2026, 7, 28, 8, 9, 10, tzinfo=UTC),
    )

    fields = message.to_redis_fields()

    assert fields == {
        "schema_version": "1",
        "message_id": "msg-1",
        "trace_id": "trace-1",
        "request_id": "request-1",
        "job_id": "job-1",
        "item_id": "item-1",
        "operation_id": "operation-1",
        "operation_type": "generate_image",
        "user_id": "user-1",
        "created_at": "2026-07-28T08:09:10Z",
    }
    assert TaskMessage.from_redis_fields(fields) == message


def test_task_message_rejects_unknown_or_missing_fields() -> None:
    valid = TaskMessage(
        schema_version=1,
        message_id="msg-1",
        trace_id="trace-1",
        request_id="request-1",
        job_id="job-1",
        item_id="item-1",
        operation_id="operation-1",
        operation_type=OperationType.GENERATE_IMAGE,
        user_id="user-1",
        created_at=datetime(2026, 7, 28, tzinfo=UTC),
    ).to_redis_fields()

    with pytest.raises(InvalidTaskMessage):
        TaskMessage.from_redis_fields({**valid, "final_prompt": "secret prompt"})
    without_item = {key: value for key, value in valid.items() if key != "item_id"}
    with pytest.raises(InvalidTaskMessage):
        TaskMessage.from_redis_fields(without_item)


def test_state_machine_allows_declared_path_and_rejects_skips() -> None:
    path = (
        GenerationItemStatus.WAITING,
        GenerationItemStatus.QUEUED,
        GenerationItemStatus.CLAIMED,
        GenerationItemStatus.SUBMITTING,
        GenerationItemStatus.SUBMITTED,
        GenerationItemStatus.PROCESSING,
        GenerationItemStatus.STORING,
        GenerationItemStatus.GENERATED,
    )

    for current, target in pairwise(path):
        require_transition(current, target)

    with pytest.raises(InvalidTaskTransition):
        require_transition(GenerationItemStatus.QUEUED, GenerationItemStatus.GENERATED)
    with pytest.raises(InvalidTaskTransition):
        require_transition(GenerationItemStatus.GENERATED, GenerationItemStatus.QUEUED)


@pytest.mark.parametrize(
    "status",
    [
        GenerationItemStatus.GENERATED,
        GenerationItemStatus.CANCELLED,
        GenerationItemStatus.TIMED_OUT,
        GenerationItemStatus.FAILED,
        GenerationItemStatus.SUBMISSION_UNCERTAIN,
    ],
)
def test_terminal_states_cannot_transition(status: GenerationItemStatus) -> None:
    assert is_terminal(status) is True
    with pytest.raises(InvalidTaskTransition):
        require_transition(status, GenerationItemStatus.QUEUED)


def test_execution_snapshot_keeps_object_keys_not_urls_or_bytes() -> None:
    spec = GenerationItemSpec(
        item_id="item-1",
        operation_id="operation-1",
        sequence=1,
        image_type="白底",
        operation_type=OperationType.GENERATE_IMAGE,
        render_tier=RenderTier.STANDARD,
        final_prompt="make a faithful product image",
        model="gpt-image-2",
        ratio="1:1",
        size=(1024, 1024),
        quality=None,
        seed=0,
        references=(
            ReferenceSnapshot(
                source=ReferenceSource.UPLOAD,
                object_key="user-1/product.png",
                role="product",
                order=0,
            ),
        ),
        reserved_cost=Decimal("0.05"),
    )

    assert spec.references[0].object_key == "user-1/product.png"
    assert not hasattr(spec.references[0], "url")
    assert not hasattr(spec.references[0], "data")


@pytest.mark.parametrize(
    ("sequence", "size", "cost"),
    [
        (0, (1024, 1024), Decimal("0.05")),
        (1, (0, 1024), Decimal("0.05")),
        (1, (1024, 1024), Decimal("-0.01")),
    ],
)
def test_execution_snapshot_rejects_invalid_boundaries(
    sequence: int, size: tuple[int, int], cost: Decimal
) -> None:
    with pytest.raises(ValueError):
        GenerationItemSpec(
            item_id="item-1",
            operation_id="operation-1",
            sequence=sequence,
            image_type=None,
            operation_type=OperationType.GENERATE_IMAGE,
            render_tier=RenderTier.STANDARD,
            final_prompt="prompt",
            model="gpt-image-2",
            ratio="1:1",
            size=size,
            quality=None,
            seed=0,
            references=(),
            reserved_cost=cost,
        )


def test_execution_snapshot_keeps_a_non_empty_stable_model_id() -> None:
    spec = GenerationItemSpec(
        item_id="item-1",
        operation_id="operation-1",
        sequence=1,
        image_type=None,
        operation_type=OperationType.GENERATE_IMAGE,
        render_tier=RenderTier.FOUR_K,
        final_prompt="render",
        model="gpt-image-2",
        ratio="16:9",
        size=(3840, 2160),
        quality="high",
        seed=1,
        references=(),
        reserved_cost=Decimal("0.18"),
    )

    assert spec.model == "gpt-image-2"

    with pytest.raises(ValueError, match="model"):
        GenerationItemSpec(
            item_id="item-2",
            operation_id="operation-2",
            sequence=1,
            image_type=None,
            operation_type=OperationType.GENERATE_IMAGE,
            render_tier=RenderTier.STANDARD,
            final_prompt="render",
            model="",
            ratio="1:1",
            size=(1024, 1024),
            quality=None,
            seed=1,
            references=(),
            reserved_cost=Decimal("0.05"),
        )
