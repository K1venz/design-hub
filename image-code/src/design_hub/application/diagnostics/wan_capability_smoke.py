from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from io import BytesIO

from PIL import Image, UnidentifiedImageError

SMOKE_RATIOS = ("1:4", "4:1", "1:8", "8:1")
RATIO_TOLERANCE = 0.03


@dataclass(frozen=True)
class SmokeResult:
    ratio: str
    requested_size: tuple[int, int]
    task_id: str
    status: str
    actual_size: tuple[int, int]
    latency_ms: int
    artifact_path: str


def image_dimensions(data: bytes) -> tuple[int, int]:
    try:
        with Image.open(BytesIO(data)) as image:
            size = image.size
            image.verify()
    except (UnidentifiedImageError, OSError) as exc:
        raise ValueError("Wan smoke result is not a valid image") from exc
    return size


def build_evidence(results: list[SmokeResult]) -> dict[str, object]:
    by_ratio: dict[str, SmokeResult] = {}
    for result in results:
        if result.ratio in by_ratio:
            raise ValueError("each Wan smoke ratio must appear exactly once")
        by_ratio[result.ratio] = result
    if tuple(by_ratio) != SMOKE_RATIOS:
        raise ValueError("each Wan smoke ratio must appear exactly once")

    rows: list[dict[str, object]] = []
    for ratio in SMOKE_RATIOS:
        result = by_ratio[ratio]
        if result.status != "passed":
            raise ValueError(f"Wan smoke ratio {ratio} did not pass")
        target = _ratio_value(ratio)
        actual = result.actual_size[0] / result.actual_size[1]
        ratio_error = abs(actual - target) / target
        if ratio_error > RATIO_TOLERANCE:
            raise ValueError(f"Wan smoke ratio {ratio} exceeds ratio tolerance")
        row = asdict(result)
        row["requested_size"] = list(result.requested_size)
        row["actual_size"] = list(result.actual_size)
        row["ratio_error"] = round(ratio_error, 6)
        rows.append(row)

    return {
        "model": "wan2.7-image-pro",
        "render_tier": "standard",
        "passed": True,
        "ratio_tolerance": RATIO_TOLERANCE,
        "generated_at": datetime.now(UTC).isoformat(),
        "results": rows,
    }


def _ratio_value(ratio: str) -> float:
    width, height = (int(value) for value in ratio.split(":"))
    return width / height
