from io import BytesIO

import pytest
from PIL import Image

from design_hub.application.diagnostics.wan_capability_smoke import (
    SMOKE_RATIOS,
    SmokeResult,
    build_evidence,
    image_dimensions,
)


def _png(width: int, height: int) -> bytes:
    buffer = BytesIO()
    Image.new("RGB", (width, height), "white").save(buffer, format="PNG")
    return buffer.getvalue()


def test_image_dimensions_reads_the_generated_file() -> None:
    assert image_dimensions(_png(640, 2560)) == (640, 2560)


def test_build_evidence_accepts_all_four_extreme_ratios() -> None:
    sizes = {
        "1:4": (640, 2560),
        "4:1": (2560, 640),
        "1:8": (448, 3584),
        "8:1": (3584, 448),
    }
    results = [
        SmokeResult(
            ratio=ratio,
            requested_size=size,
            task_id=f"task-{index}",
            status="passed",
            actual_size=size,
            latency_ms=100 + index,
            artifact_path=f"exports/wan-capability-smoke/{ratio.replace(':', 'x')}.png",
        )
        for index, (ratio, size) in enumerate(sizes.items(), start=1)
    ]

    evidence = build_evidence(results)

    assert evidence["passed"] is True
    assert [item["ratio"] for item in evidence["results"]] == list(
        SMOKE_RATIOS
    )
    assert all(item["ratio_error"] == 0 for item in evidence["results"])
    assert "url" not in str(evidence).lower()
    assert "api_key" not in str(evidence).lower()


def test_build_evidence_rejects_missing_or_distorted_results() -> None:
    with pytest.raises(ValueError, match="exactly once"):
        build_evidence([])

    results = [
        SmokeResult(
            ratio=ratio,
            requested_size=(640, 2560),
            task_id=f"task-{index}",
            status="passed",
            actual_size=(1000, 1000),
            latency_ms=100,
            artifact_path=f"{index}.png",
        )
        for index, ratio in enumerate(SMOKE_RATIOS)
    ]
    with pytest.raises(ValueError, match="ratio tolerance"):
        build_evidence(results)
