import sys
from argparse import Namespace
from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path

import pytest

_SCRIPT = Path(__file__).parents[1] / "scripts" / "load_test_stage_a.py"
_SPEC = spec_from_file_location("load_test_stage_a", _SCRIPT)
assert _SPEC is not None and _SPEC.loader is not None
_MODULE = module_from_spec(_SPEC)
sys.modules[_SPEC.name] = _MODULE
_SPEC.loader.exec_module(_MODULE)

GenerationObservation = _MODULE.GenerationObservation
percentile = _MODULE.percentile
summarize = _MODULE.summarize
validate_args = _MODULE.validate_args


def test_percentile_interpolates_sorted_samples() -> None:
    assert percentile([4.0, 1.0, 3.0, 2.0], 0.5) == 2.5
    assert percentile([], 0.95) is None


def test_real_provider_requires_explicit_cost_acknowledgement() -> None:
    args = Namespace(
        provider="real",
        allow_real_provider=False,
        writers=40,
        images_per_job=5,
        unit_cost=0.05,
    )
    with pytest.raises(ValueError, match="allow-real-provider"):
        validate_args(args)


def test_summary_counts_duplicate_image_events_and_completion() -> None:
    observations = [
        GenerationObservation(
            job_id="job-1",
            api_seconds=0.1,
            queue_wait_seconds=0.2,
            completion_seconds=1.0,
            image_item_ids=("item-1", "item-2", "item-2"),
            terminal_event="task_completed",
            error=None,
        ),
        GenerationObservation(
            job_id="job-2",
            api_seconds=0.2,
            queue_wait_seconds=None,
            completion_seconds=None,
            image_item_ids=(),
            terminal_event=None,
            error="timeout",
        ),
    ]

    report = summarize(observations, read_latencies=[0.01, 0.02])

    assert report["completed_jobs"] == 1
    assert report["failed_jobs"] == 1
    assert report["duplicate_image_events"] == 1
    assert report["api_p95_ms"] == pytest.approx(195)
