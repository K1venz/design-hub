import json
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from design_hub.application.admin.runtime_log_service import RuntimeLogService
from design_hub.domain.enums import Role
from design_hub.domain.models import AuthUser
from design_hub.domain.runtime_logs import (
    RuntimeLogCorruptError,
    RuntimeLogQuery,
)
from design_hub.infrastructure.monitoring.runtime_log_files import (
    FileRuntimeLogRepository,
)
from design_hub.interface.api.app import register_error_handlers
from design_hub.interface.api.deps import get_current_user
from design_hub.interface.api.routes import runtime_logs


def _event(
    event_id: str,
    timestamp: str,
    *,
    level: str = "info",
    service: str = "api",
    chain: str = "image_generation",
    trace_id: str | None = "trace-1",
    prompt: str | None = None,
) -> dict[str, object]:
    return {
        "event_id": event_id,
        "timestamp": timestamp,
        "level": level,
        "service": service,
        "chain": chain,
        "event": f"event_{event_id}",
        "action": f"动作 {event_id}",
        "logger": "design_hub.application.tasking.worker",
        "function": "run_item",
        "trace_id": trace_id,
        "job_id": "job-1",
        "model": "gpt-image-2",
        "status": "completed",
        "duration_ms": 120,
        "prompt": prompt,
    }


def _write(path: Path, *rows: dict[str, object]) -> None:
    path.write_text(
        "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows),
        encoding="utf-8",
    )


def _repository(tmp_path: Path) -> FileRuntimeLogRepository:
    _write(
        tmp_path / "api.jsonl",
        _event(
            "warning-new",
            "2026-07-31T09:05:00Z",
            level="warning",
            prompt="完整提示词",
        ),
        _event("completed", "2026-07-31T09:04:00Z"),
    )
    _write(
        tmp_path / "api.jsonl.1",
        _event(
            "warning-old",
            "2026-07-31T09:01:00Z",
            level="warning",
        ),
        _event("created", "2026-07-31T09:00:00Z"),
    )
    _write(
        tmp_path / "worker.jsonl",
        _event(
            "published",
            "2026-07-31T09:02:00Z",
            service="worker",
        ),
    )
    _write(
        tmp_path / "worker.jsonl.1",
        _event(
            "other-trace",
            "2026-07-31T08:59:00Z",
            service="worker",
            trace_id="trace-2",
        ),
    )
    return FileRuntimeLogRepository(tmp_path)


def test_file_repository_filters_pages_and_reads_detail_and_trace(
    tmp_path: Path,
) -> None:
    repository = _repository(tmp_path)

    page = repository.list(
        RuntimeLogQuery(level="warning", chain="image_generation"),
        limit=20,
        offset=0,
    )

    assert [item.event_id for item in page.items] == [
        "warning-new",
        "warning-old",
    ]
    assert page.total == 2
    assert page.limit == 20
    assert page.offset == 0
    detail = repository.get("warning-new")
    assert detail is not None
    assert detail.prompt == "完整提示词"
    assert [item.event_id for item in repository.trace("trace-1")] == [
        "created",
        "warning-old",
        "published",
        "completed",
        "warning-new",
    ]


def test_file_repository_reports_corrupt_filename_and_line_without_payload(
    tmp_path: Path,
) -> None:
    secret_payload = "Bearer private-token full private prompt"
    (tmp_path / "api.jsonl").write_text(
        json.dumps(_event("valid", "2026-07-31T09:00:00Z"))
        + "\n"
        + secret_payload
        + "\n",
        encoding="utf-8",
    )
    repository = FileRuntimeLogRepository(tmp_path)

    with pytest.raises(RuntimeLogCorruptError) as captured:
        repository.list(RuntimeLogQuery(), limit=20, offset=0)

    assert str(captured.value) == "api.jsonl:2"
    assert secret_payload not in str(captured.value)


def _client(tmp_path: Path, role: Role = Role.MANAGER) -> TestClient:
    app = FastAPI()
    app.state.runtime_log_service = RuntimeLogService(_repository(tmp_path))
    app.include_router(runtime_logs.router)
    register_error_handlers(app)

    async def current_user() -> AuthUser:
        return AuthUser(
            user_id="1",
            name="测试管理员",
            role=role,
            dept=None,
        )

    app.dependency_overrides[get_current_user] = current_user
    return TestClient(app, raise_server_exceptions=False)


def test_manager_runtime_log_api_keeps_prompt_out_of_list_and_in_detail(
    tmp_path: Path,
) -> None:
    client = _client(tmp_path)

    listed = client.get("/admin/runtime-logs?limit=2&offset=0")
    detailed = client.get("/admin/runtime-logs/warning-new")
    traced = client.get("/admin/runtime-logs/warning-new/trace")

    assert listed.status_code == 200
    assert listed.json()["total"] == 6
    assert len(listed.json()["items"]) == 2
    assert all("prompt" not in item for item in listed.json()["items"])
    assert detailed.status_code == 200
    assert detailed.json()["prompt"] == "完整提示词"
    assert traced.status_code == 200
    assert [item["event_id"] for item in traced.json()] == [
        "created",
        "warning-old",
        "published",
        "completed",
        "warning-new",
    ]


def test_runtime_log_api_enforces_manager_role_and_not_found(
    tmp_path: Path,
) -> None:
    assert _client(tmp_path, Role.DESIGNER).get(
        "/admin/runtime-logs"
    ).status_code == 403
    assert _client(tmp_path).get(
        "/admin/runtime-logs/missing"
    ).status_code == 404


@pytest.mark.parametrize(
    "query",
    [
        "limit=0",
        "limit=201",
        "offset=-1",
        "level=debug",
        "service=frontend",
        "start=2026-07-31T10:00:00Z&end=2026-07-31T09:00:00Z",
    ],
)
def test_runtime_log_api_rejects_invalid_filters(
    tmp_path: Path,
    query: str,
) -> None:
    response = _client(tmp_path).get(f"/admin/runtime-logs?{query}")

    assert response.status_code in {400, 422}
