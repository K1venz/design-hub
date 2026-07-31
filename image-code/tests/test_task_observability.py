import io
import json
import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.testclient import TestClient
from prometheus_client import CollectorRegistry, generate_latest
from structlog.contextvars import (
    bind_contextvars,
    clear_contextvars,
    get_contextvars,
)

from design_hub.config.settings import Settings
from design_hub.infrastructure.monitoring.logging import (
    configure_logging,
    install_request_context,
    sanitize_event,
    scrub_sentry_event,
    set_sentry_task_context,
)
from design_hub.infrastructure.monitoring.task_metrics import TaskMetrics


def _restore_root_logging(
    handlers: list[logging.Handler],
    level: int,
) -> None:
    root = logging.getLogger()
    for handler in root.handlers:
        handler.close()
    root.handlers.clear()
    root.handlers.extend(handlers)
    root.setLevel(level)


def test_runtime_file_only_contains_explicit_business_chain_logs(
    tmp_path: Path,
) -> None:
    stream = io.StringIO()
    root = logging.getLogger()
    original_handlers = list(root.handlers)
    original_level = root.level
    try:
        configure_logging(
            stream=stream,
            runtime_log_dir=tmp_path,
            service="api",
            runtime_log_max_bytes=1024,
        )
        logger = logging.getLogger("design_hub.example")
        logger.info("ordinary_internal_event")
        logger.info(
            "generation_task_created",
            extra={
                "chain": "image_generation",
                "action": "创建出图任务",
                "trace_id": "trace-1",
                "prompt": "完整提示词",
            },
        )
    finally:
        _restore_root_logging(original_handlers, original_level)

    rows = [
        json.loads(line)
        for line in (tmp_path / "api.jsonl").read_text().splitlines()
    ]
    assert len(rows) == 1
    assert rows[0]["event"] == "generation_task_created"
    assert rows[0]["function"] == (
        "test_runtime_file_only_contains_explicit_business_chain_logs"
    )
    assert rows[0]["prompt"] == "完整提示词"


def test_runtime_file_excludes_uvicorn_and_stdout_excludes_prompt(
    tmp_path: Path,
) -> None:
    stream = io.StringIO()
    root = logging.getLogger()
    original_handlers = list(root.handlers)
    original_level = root.level
    try:
        configure_logging(
            stream=stream,
            runtime_log_dir=tmp_path,
            service="api",
        )
        context = {
            "chain": "image_generation",
            "action": "开始调用图片模型",
            "prompt": "只允许管理员在详情中查看",
        }
        logging.getLogger("uvicorn.access").info(
            "access_with_business_fields",
            extra=context,
        )
        logging.getLogger("design_hub.worker").info(
            "generation_provider_submit_started",
            extra=context,
        )
    finally:
        _restore_root_logging(original_handlers, original_level)

    rows = [
        json.loads(line)
        for line in (tmp_path / "api.jsonl").read_text().splitlines()
    ]
    assert [row["event"] for row in rows] == [
        "generation_provider_submit_started"
    ]
    assert "只允许管理员在详情中查看" not in stream.getvalue()


def test_runtime_prompt_is_complete_but_secret_patterns_are_redacted(
    tmp_path: Path,
) -> None:
    root = logging.getLogger()
    original_handlers = list(root.handlers)
    original_level = root.level
    long_prefix = "商品提示词" * 250
    try:
        configure_logging(
            stream=io.StringIO(),
            runtime_log_dir=tmp_path,
            service="worker",
        )
        logging.getLogger("design_hub.worker").info(
            "generation_provider_submit_started",
            extra={
                "chain": "image_generation",
                "action": "开始调用图片模型",
                "prompt": (
                    f"{long_prefix} Bearer abc.def sk-secret123 "
                    "password=private "
                    "https://cdn.example/a.png?signature=private"
                ),
            },
        )
    finally:
        _restore_root_logging(original_handlers, original_level)

    row = json.loads((tmp_path / "worker.jsonl").read_text())
    prompt = row["prompt"]
    assert prompt.startswith(long_prefix)
    assert len(prompt) > 1000
    assert "Bearer [REDACTED]" in prompt
    assert "sk-[REDACTED]" in prompt
    assert "password=[REDACTED]" in prompt
    assert "https://cdn.example/a.png?[REDACTED]" in prompt
    for secret in ("abc.def", "secret123", "private"):
        assert secret not in prompt


def test_runtime_files_are_bounded_and_distinct_per_service(
    tmp_path: Path,
) -> None:
    root = logging.getLogger()
    original_handlers = list(root.handlers)
    original_level = root.level
    max_bytes = 50 * 1024 * 1024
    try:
        configure_logging(
            stream=io.StringIO(),
            runtime_log_dir=tmp_path,
            service="api",
            runtime_log_max_bytes=max_bytes,
        )
        api_handler = next(
            handler
            for handler in root.handlers
            if isinstance(handler, RotatingFileHandler)
        )
        assert Path(api_handler.baseFilename).name == "api.jsonl"
        assert api_handler.maxBytes == max_bytes
        assert api_handler.backupCount == 1

        configure_logging(
            stream=io.StringIO(),
            runtime_log_dir=tmp_path,
            service="worker",
            runtime_log_max_bytes=max_bytes,
        )
        worker_handler = next(
            handler
            for handler in root.handlers
            if isinstance(handler, RotatingFileHandler)
        )
        assert Path(worker_handler.baseFilename).name == "worker.jsonl"
    finally:
        _restore_root_logging(original_handlers, original_level)

    settings = Settings()
    assert settings.runtime_log_dir == Path("./exports/.runtime-logs")
    assert settings.runtime_log_max_bytes == max_bytes


def test_runtime_file_failure_does_not_fail_business_logging(
    tmp_path: Path,
    monkeypatch,
    capsys,
) -> None:
    captured: list[BaseException] = []
    monkeypatch.setattr(
        "design_hub.infrastructure.monitoring.runtime_log_files."
        "sentry_sdk.capture_exception",
        captured.append,
    )
    root = logging.getLogger()
    original_handlers = list(root.handlers)
    original_level = root.level
    try:
        configure_logging(
            stream=io.StringIO(),
            runtime_log_dir=tmp_path,
            service="api",
        )
        handler = next(
            item
            for item in root.handlers
            if isinstance(item, RotatingFileHandler)
        )

        class BrokenStream:
            def write(self, value: str) -> int:
                del value
                raise OSError("contains-private-path")

            def flush(self) -> None:
                return None

            def tell(self) -> int:
                return 0

            def seek(self, offset: int, whence: int = 0) -> int:
                del offset, whence
                return 0

            def close(self) -> None:
                return None

        handler.stream = BrokenStream()
        logger = logging.getLogger("design_hub.worker")
        context = {"chain": "image_generation", "action": "创建出图任务"}
        logger.info("generation_task_created", extra=context)
        logger.info("generation_task_created", extra=context)
    finally:
        _restore_root_logging(original_handlers, original_level)

    assert len(captured) == 2
    assert capsys.readouterr().err.count(
        "runtime business log write failed"
    ) == 1


def test_log_allowlist_keeps_correlation_and_removes_sensitive_payloads() -> None:
    event = sanitize_event(
        None,
        "error",
        {
            "event": "generation_provider_failed",
            "request_id": "request-1",
            "trace_id": "trace-1",
            "job_id": "job-1",
            "item_id": "item-1",
            "operation_id": "operation-1",
            "authorization": "Bearer secret-token",
            "api_key": "sk-secret",
            "prompt": "full private prompt",
            "image_bytes": b"private-image",
            "signed_url": "https://cdn.example/a.png?signature=secret",
            "redis_url": "redis://user:password@redis:6379/0",
            "error_summary": (
                "upstream https://cdn.example/a.png?signature=secret "
                "Bearer secret-token sk-secret"
            ),
        },
    )
    rendered = json.dumps(event)

    assert event["request_id"] == "request-1"
    assert event["trace_id"] == "trace-1"
    assert event["job_id"] == "job-1"
    assert event["item_id"] == "item-1"
    assert event["operation_id"] == "operation-1"
    for secret in (
        "secret-token",
        "sk-secret",
        "full private prompt",
        "private-image",
        "signature=secret",
        "password",
    ):
        assert secret not in rendered


def test_stdlib_pipeline_logs_keep_one_correlation_chain() -> None:
    stream = io.StringIO()
    root = logging.getLogger()
    original_handlers = list(root.handlers)
    original_level = root.level
    try:
        configure_logging(stream=stream)
        bind_contextvars(request_id="request-1", trace_id="trace-1")
        context = {
            "job_id": "job-1",
            "item_id": "item-1",
            "operation_id": "operation-1",
            "prompt": "must not be logged",
        }
        for logger_name, event in (
            ("submission", "generation_submission_accepted"),
            ("outbox", "generation_outbox_published"),
            ("worker", "generation_item_claimed"),
            ("provider", "generation_provider_submit_started"),
        ):
            logging.getLogger(logger_name).info(event, extra=context)
    finally:
        clear_contextvars()
        root.handlers.clear()
        root.handlers.extend(original_handlers)
        root.setLevel(original_level)

    records = [json.loads(line) for line in stream.getvalue().splitlines()]
    assert len(records) == 4
    assert {record["request_id"] for record in records} == {"request-1"}
    assert {record["trace_id"] for record in records} == {"trace-1"}
    assert {record["job_id"] for record in records} == {"job-1"}
    assert {record["item_id"] for record in records} == {"item-1"}
    assert {record["operation_id"] for record in records} == {"operation-1"}
    assert "must not be logged" not in stream.getvalue()


def test_configure_logging_routes_uvicorn_access_logs_through_redaction() -> None:
    safe_stream = io.StringIO()
    bypass_stream = io.StringIO()
    root = logging.getLogger()
    access = logging.getLogger("uvicorn.access")
    original_root_handlers = list(root.handlers)
    original_root_level = root.level
    original_access_handlers = list(access.handlers)
    original_access_level = access.level
    original_access_propagate = access.propagate
    try:
        access.handlers = [logging.StreamHandler(bypass_stream)]
        access.setLevel(logging.INFO)
        access.propagate = False

        configure_logging(stream=safe_stream)
        access.info(
            '%s - "%s %s HTTP/%s" %d',
            "127.0.0.1:12345",
            "GET",
            "/listing/job-1/events?access_token=secret-jwt",
            "1.1",
            200,
        )
    finally:
        root.handlers.clear()
        root.handlers.extend(original_root_handlers)
        root.setLevel(original_root_level)
        access.handlers = original_access_handlers
        access.setLevel(original_access_level)
        access.propagate = original_access_propagate

    rendered = safe_stream.getvalue() + bypass_stream.getvalue()
    assert "secret-jwt" not in rendered
    assert "access_token=[REDACTED]" in safe_stream.getvalue()
    assert bypass_stream.getvalue() == ""


def test_exception_logs_keep_safe_type_and_frames_without_message_or_locals() -> None:
    stream = io.StringIO()
    root = logging.getLogger()
    original_handlers = list(root.handlers)
    original_level = root.level
    try:
        configure_logging(stream=stream)
        private_prompt = "private-product-prompt"
        try:
            raise RuntimeError(f"database rejected {private_prompt}")
        except RuntimeError:
            logging.getLogger("uvicorn.error").exception(
                "Exception in ASGI application"
            )
    finally:
        root.handlers.clear()
        root.handlers.extend(original_handlers)
        root.setLevel(original_level)

    record = json.loads(stream.getvalue())
    assert record["error_type"] == "RuntimeError"
    assert "test_task_observability.py:" in record["error_summary"]
    assert "private-product-prompt" not in stream.getvalue()
    assert "database rejected" not in stream.getvalue()


def test_request_context_accepts_valid_id_generates_invalid_id_and_clears() -> None:
    app = FastAPI()
    install_request_context(app)

    @app.get("/context")
    async def context(request: Request) -> dict[str, str]:
        bound = get_contextvars()
        return {
            "request_id": request.state.request_id,
            "trace_id": request.state.trace_id,
            "bound_request_id": str(bound["request_id"]),
        }

    client = TestClient(app)
    accepted = client.get("/context", headers={"X-Request-ID": "client-123"})
    generated = client.get(
        "/context",
        headers={"X-Request-ID": "Bearer invalid value"},
    )

    assert accepted.status_code == 200
    assert accepted.headers["X-Request-ID"] == "client-123"
    assert accepted.json() == {
        "request_id": "client-123",
        "trace_id": "client-123",
        "bound_request_id": "client-123",
    }
    generated_id = generated.headers["X-Request-ID"]
    assert generated_id != "Bearer invalid value"
    assert generated.json()["request_id"] == generated_id
    assert get_contextvars() == {}


def test_sentry_scrubber_removes_request_secrets_and_keeps_safe_tags() -> None:
    event = {
        "request": {
            "headers": {
                "Authorization": "Bearer secret",
                "Cookie": "session=secret",
                "User-Agent": "test",
            },
            "query_string": "access_token=secret",
            "data": {"prompt": "full private prompt"},
        },
        "extra": {
            "request_id": "request-1",
            "prompt": "full private prompt",
            "signed_url": "https://cdn/a?signature=secret",
        },
        "exception": {
            "values": [
                {
                    "type": "ProviderError",
                    "value": "sk-secret full private prompt",
                }
            ]
        },
    }

    scrubbed = scrub_sentry_event(event, {})
    rendered = json.dumps(scrubbed)

    assert scrubbed is not None
    assert scrubbed["request"]["headers"] == {"User-Agent": "test"}
    assert scrubbed["extra"] == {"request_id": "request-1"}
    assert scrubbed["exception"]["values"][0]["value"] == "ProviderError"
    for secret in (
        "Bearer secret",
        "session=secret",
        "access_token",
        "sk-secret",
        "full private prompt",
    ):
        assert secret not in rendered


def test_sentry_context_only_sets_low_cardinality_diagnostic_tags(
    monkeypatch,
) -> None:
    tags: list[tuple[str, str]] = []
    monkeypatch.setattr(
        "design_hub.infrastructure.monitoring.logging.sentry_sdk.set_tag",
        lambda key, value: tags.append((key, value)),
    )

    set_sentry_task_context(
        request_id="request-1",
        job_id="job-1",
        item_id="item-1",
        provider="gpt-image-2",
        error_code="timeout",
    )

    assert tags == [
        ("request_id", "request-1"),
        ("job_id", "job-1"),
        ("item_id", "item-1"),
        ("provider", "gpt-image-2"),
        ("error_code", "timeout"),
    ]


def test_task_metrics_cover_queue_provider_failures_duration_and_sse() -> None:
    registry = CollectorRegistry()
    metrics = TaskMetrics(registry=registry)

    metrics.set_outbox(pending=4, oldest_age_seconds=12.5)
    metrics.set_stream(depth=20, pending=3)
    metrics.set_item_state("processing", 2)
    metrics.provider_started("gpt-image-2", "standard")
    metrics.provider_finished("gpt-image-2", "standard")
    metrics.observe_item_duration("generated", 8.2)
    metrics.record_uncertain("gpt-image-2")
    metrics.record_failure("provider_timeout")
    metrics.sse_opened()
    metrics.sse_closed()

    output = generate_latest(registry).decode()
    assert 'design_hub_generation_outbox_pending 4.0' in output
    assert 'design_hub_generation_stream_depth 20.0' in output
    assert 'design_hub_generation_stream_pending 3.0' in output
    assert (
        'design_hub_generation_item_state{status="processing"} 2.0'
        in output
    )
    assert (
        'design_hub_generation_provider_in_flight{provider="gpt-image-2",tier="standard"} 0.0'
        in output
    )
    assert (
        'design_hub_generation_submission_uncertain_total{provider="gpt-image-2"} 1.0'
        in output
    )
    assert (
        'design_hub_generation_failures_total{error_code="provider_timeout"} 1.0'
        in output
    )
    assert "design_hub_generation_sse_connections 0.0" in output
