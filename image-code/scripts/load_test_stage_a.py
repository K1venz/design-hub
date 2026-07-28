"""Bounded Stage A API/SSE capacity harness.

The credential file is JSON:

[
  {"token": "<JWT>", "upload_id": "<owned upload id>"},
  {"token": "<JWT>"}
]

The first ``--writers`` entries need an upload_id. Tokens are never printed.
"""

import argparse
import asyncio
import json
import math
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any
from uuid import uuid4

import httpx

_TERMINAL_EVENTS = {"task_completed", "task_failed"}


@dataclass(frozen=True)
class LoadUser:
    token: str
    upload_id: str | None


@dataclass(frozen=True)
class GenerationObservation:
    job_id: str | None
    api_seconds: float | None
    queue_wait_seconds: float | None
    completion_seconds: float | None
    image_item_ids: tuple[str, ...]
    terminal_event: str | None
    error: str | None


def percentile(values: list[float], quantile: float) -> float | None:
    if not values:
        return None
    if not 0 <= quantile <= 1:
        raise ValueError("quantile must be between zero and one")
    ordered = sorted(values)
    position = (len(ordered) - 1) * quantile
    lower = math.floor(position)
    upper = math.ceil(position)
    if lower == upper:
        return ordered[lower]
    fraction = position - lower
    return ordered[lower] + (ordered[upper] - ordered[lower]) * fraction


def _milliseconds(value: float | None) -> float | None:
    return None if value is None else round(value * 1000, 2)


def summarize(
    observations: list[GenerationObservation],
    *,
    read_latencies: list[float],
) -> dict[str, int | float | None]:
    api = [
        observation.api_seconds
        for observation in observations
        if observation.api_seconds is not None
    ]
    queue = [
        observation.queue_wait_seconds
        for observation in observations
        if observation.queue_wait_seconds is not None
    ]
    completion = [
        observation.completion_seconds
        for observation in observations
        if observation.completion_seconds is not None
    ]
    duplicate_events = sum(
        len(observation.image_item_ids) - len(set(observation.image_item_ids))
        for observation in observations
    )
    completed = sum(
        observation.terminal_event == "task_completed"
        for observation in observations
    )
    return {
        "submitted_jobs": len(api),
        "completed_jobs": completed,
        "failed_jobs": len(observations) - completed,
        "duplicate_image_events": duplicate_events,
        "api_p50_ms": _milliseconds(percentile(api, 0.50)),
        "api_p95_ms": _milliseconds(percentile(api, 0.95)),
        "read_p50_ms": _milliseconds(percentile(read_latencies, 0.50)),
        "read_p95_ms": _milliseconds(percentile(read_latencies, 0.95)),
        "queue_wait_p50_ms": _milliseconds(percentile(queue, 0.50)),
        "queue_wait_p95_ms": _milliseconds(percentile(queue, 0.95)),
        "completion_p50_ms": _milliseconds(percentile(completion, 0.50)),
        "completion_p95_ms": _milliseconds(percentile(completion, 0.95)),
    }


def validate_args(args: argparse.Namespace) -> None:
    if args.provider == "real" and not args.allow_real_provider:
        raise ValueError(
            "real provider load requires --allow-real-provider after cost review"
        )
    if args.sessions <= 0 or args.writers <= 0:
        raise ValueError("sessions and writers must be positive")
    if args.writers > args.sessions:
        raise ValueError("writers must not exceed sessions")
    if not 3 <= args.images_per_job <= 10:
        raise ValueError("images-per-job must be between 3 and 10")
    if args.max_concurrency <= 0:
        raise ValueError("max-concurrency must be positive")
    if args.unit_cost < 0:
        raise ValueError("unit-cost must be non-negative")


def _load_users(path: Path, *, sessions: int, writers: int) -> list[LoadUser]:
    parsed = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(parsed, list):
        raise ValueError("users file must contain a JSON array")
    users: list[LoadUser] = []
    for index, item in enumerate(parsed):
        if not isinstance(item, dict):
            raise ValueError(f"users[{index}] must be an object")
        token = item.get("token")
        upload_id = item.get("upload_id")
        if not isinstance(token, str) or not token:
            raise ValueError(f"users[{index}].token must be a non-empty string")
        if upload_id is not None and (
            not isinstance(upload_id, str) or not upload_id
        ):
            raise ValueError(
                f"users[{index}].upload_id must be a non-empty string"
            )
        users.append(LoadUser(token=token, upload_id=upload_id))
    if len(users) < sessions:
        raise ValueError(
            f"users file needs at least {sessions} entries; got {len(users)}"
        )
    missing_uploads = [
        index for index, user in enumerate(users[:writers]) if user.upload_id is None
    ]
    if missing_uploads:
        raise ValueError(
            "writer entries need upload_id; missing indexes: "
            + ",".join(str(index) for index in missing_uploads)
        )
    return users[:sessions]


def _plan(image_count: int) -> dict[str, int]:
    scene_count = (image_count - 1) // 2
    return {
        "白底": 1,
        "场景": scene_count,
        "卖点": image_count - scene_count - 1,
    }


async def _read_probe(
    client: httpx.AsyncClient,
    semaphore: asyncio.Semaphore,
    user: LoadUser,
) -> tuple[float | None, str | None]:
    started = time.perf_counter()
    try:
        async with semaphore:
            response = await client.get(
                "/listing/jobs",
                params={"limit": 1},
                headers={"Authorization": f"Bearer {user.token}"},
            )
        response.raise_for_status()
    except httpx.HTTPError as exc:
        return None, type(exc).__name__
    return time.perf_counter() - started, None


async def _await_events(
    client: httpx.AsyncClient,
    semaphore: asyncio.Semaphore,
    *,
    user: LoadUser,
    job_id: str,
    submitted_at: float,
    sse_timeout: float,
) -> tuple[float | None, float | None, tuple[str, ...], str | None]:
    queue_wait: float | None = None
    image_item_ids: list[str] = []
    current_event: str | None = None
    current_data: dict[str, Any] = {}
    terminal: str | None = None
    timeout = httpx.Timeout(
        connect=10,
        read=sse_timeout,
        write=10,
        pool=10,
    )
    async with semaphore:
        async with client.stream(
            "GET",
            f"/listing/{job_id}/events",
            params={"access_token": user.token},
            timeout=timeout,
        ) as response:
            response.raise_for_status()
            async for line in response.aiter_lines():
                if line.startswith("event:"):
                    current_event = line.partition(":")[2].strip()
                elif line.startswith("data:"):
                    value = json.loads(line.partition(":")[2].strip())
                    current_data = value if isinstance(value, dict) else {}
                elif not line and current_event is not None:
                    elapsed = time.perf_counter() - submitted_at
                    if current_event == "task_started" and queue_wait is None:
                        queue_wait = elapsed
                    if current_event == "image_generated":
                        item_id = current_data.get("item_id")
                        if isinstance(item_id, str):
                            image_item_ids.append(item_id)
                    if current_event in _TERMINAL_EVENTS:
                        terminal = current_event
                        return (
                            queue_wait,
                            elapsed,
                            tuple(image_item_ids),
                            terminal,
                        )
                    current_event = None
                    current_data = {}
    return queue_wait, None, tuple(image_item_ids), terminal


async def _generation_probe(
    client: httpx.AsyncClient,
    semaphore: asyncio.Semaphore,
    user: LoadUser,
    *,
    images_per_job: int,
    sse_timeout: float,
) -> GenerationObservation:
    assert user.upload_id is not None
    started = time.perf_counter()
    try:
        async with semaphore:
            response = await client.post(
                "/listing/generate",
                headers={
                    "Authorization": f"Bearer {user.token}",
                    "Idempotency-Key": f"load:{uuid4().hex}",
                },
                json={
                    "upload_ids": [user.upload_id],
                    "prompt": "Stage A mock capacity probe",
                    "ratio": "1:1",
                    "plan": _plan(images_per_job),
                },
            )
        api_seconds = time.perf_counter() - started
        response.raise_for_status()
        payload = response.json()
        job_id = payload.get("job_id")
        if not isinstance(job_id, str) or not job_id:
            raise ValueError("submission response has no job_id")
        queue_wait, completion, items, terminal = await asyncio.wait_for(
            _await_events(
                client,
                semaphore,
                user=user,
                job_id=job_id,
                submitted_at=started,
                sse_timeout=sse_timeout,
            ),
            timeout=sse_timeout,
        )
        return GenerationObservation(
            job_id=job_id,
            api_seconds=api_seconds,
            queue_wait_seconds=queue_wait,
            completion_seconds=completion,
            image_item_ids=items,
            terminal_event=terminal,
            error=(
                "task_failed"
                if terminal == "task_failed"
                else None
                if terminal is not None
                else "SSE ended without terminal event"
            ),
        )
    except (TimeoutError, httpx.HTTPError, json.JSONDecodeError, ValueError) as exc:
        return GenerationObservation(
            job_id=None,
            api_seconds=None,
            queue_wait_seconds=None,
            completion_seconds=None,
            image_item_ids=(),
            terminal_event=None,
            error=type(exc).__name__,
        )


def _metric_samples(body: str) -> dict[str, float]:
    samples: dict[str, float] = {}
    for line in body.splitlines():
        if not line.startswith("design_hub_generation_"):
            continue
        key, separator, raw_value = line.rpartition(" ")
        if not separator:
            continue
        try:
            samples[key] = float(raw_value)
        except ValueError:
            continue
    return samples


async def run_load(args: argparse.Namespace) -> dict[str, object]:
    users = _load_users(
        args.users_file,
        sessions=args.sessions,
        writers=args.writers,
    )
    semaphore = asyncio.Semaphore(args.max_concurrency)
    limits = httpx.Limits(
        max_connections=args.max_concurrency,
        max_keepalive_connections=args.max_concurrency,
    )
    timeout = httpx.Timeout(args.request_timeout)
    async with httpx.AsyncClient(
        base_url=args.base_url.rstrip("/"),
        timeout=timeout,
        limits=limits,
    ) as client:
        read_tasks = [
            asyncio.create_task(_read_probe(client, semaphore, user))
            for user in users
        ]
        generation_tasks = [
            asyncio.create_task(
                _generation_probe(
                    client,
                    semaphore,
                    user,
                    images_per_job=args.images_per_job,
                    sse_timeout=args.sse_timeout,
                )
            )
            for user in users[: args.writers]
        ]
        read_results, observations = await asyncio.gather(
            asyncio.gather(*read_tasks),
            asyncio.gather(*generation_tasks),
        )
        metrics_response = await client.get("/metrics")
        metrics_response.raise_for_status()

    read_latencies = [
        latency for latency, error in read_results if latency is not None and error is None
    ]
    report: dict[str, object] = summarize(
        list(observations),
        read_latencies=read_latencies,
    )
    report["requested_sessions"] = args.sessions
    report["read_failures"] = sum(error is not None for _latency, error in read_results)
    report["requested_jobs"] = args.writers
    report["requested_images"] = args.writers * args.images_per_job
    report["maximum_estimated_cost"] = round(
        args.writers * args.images_per_job * args.unit_cost,
        2,
    )
    report["provider_mode"] = args.provider
    report["errors"] = [
        asdict(observation)
        for observation in observations
        if observation.error is not None
    ]
    report["metrics"] = _metric_samples(metrics_response.text)
    return report


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Bounded 200-session Stage A API/SSE capacity harness."
    )
    parser.add_argument("--base-url", default="http://127.0.0.1:8000")
    parser.add_argument("--users-file", type=Path, required=True)
    parser.add_argument("--sessions", type=int, default=200)
    parser.add_argument("--writers", type=int, default=40)
    parser.add_argument("--images-per-job", type=int, default=5)
    parser.add_argument("--max-concurrency", type=int, default=50)
    parser.add_argument("--request-timeout", type=float, default=30)
    parser.add_argument("--sse-timeout", type=float, default=900)
    parser.add_argument("--provider", choices=("mock", "real"), default="mock")
    parser.add_argument("--unit-cost", type=float, default=0.05)
    parser.add_argument("--allow-real-provider", action="store_true")
    parser.add_argument("--output", type=Path)
    return parser


def main() -> None:
    parser = _parser()
    args = parser.parse_args()
    try:
        validate_args(args)
    except ValueError as exc:
        parser.error(str(exc))
    maximum_cost = args.writers * args.images_per_job * args.unit_cost
    print(
        f"planned load: sessions={args.sessions}, jobs={args.writers}, "
        f"images={args.writers * args.images_per_job}, "
        f"maximum estimated cost={maximum_cost:.2f}"
    )
    report = asyncio.run(run_load(args))
    rendered = json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True)
    print(rendered)
    if args.output is not None:
        args.output.write_text(rendered + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
