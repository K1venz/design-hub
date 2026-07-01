"""两阶段落库单测（ISSUE-0047）：入队建行(生成中)→逐张增量(含失败张)→终态改状态；
进行中单可查、部分完成失败张留痕。DB 层走真实 SQLite 往返，命令层走 fakes 校验编排/时序。"""

import asyncio
from decimal import Decimal

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from design_hub.application.listing.commands import ListingGenerationCommand
from design_hub.domain.enums import ModelName, TaskEventType
from design_hub.domain.models import (
    GeneratedImage,
    ListingJobImage,
    ListingJobStart,
    ListingResult,
    TaskEvent,
)
from design_hub.infrastructure.db.base import Base
from design_hub.infrastructure.db.listing_history_repo import SqlAlchemyListingHistory
from design_hub.infrastructure.db.listing_query_repo import SqlAlchemyListingHistoryQuery
from design_hub.ports.events import EventPublisher
from design_hub.ports.listing_history import ListingHistory


async def _fresh_repos() -> tuple[SqlAlchemyListingHistory, SqlAlchemyListingHistoryQuery]:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    sf = async_sessionmaker(engine, expire_on_commit=False)
    return SqlAlchemyListingHistory(sf), SqlAlchemyListingHistoryQuery(sf)


def _start(**kw: object) -> ListingJobStart:
    base: dict[str, object] = dict(
        job_id="j1", user_id="u1", prompt="春节红", modifiers={"platform": "抖音电商"},
        ratio="1:1", size="1024x1024", n=2, upload_keys=("u1/a.png",),
    )
    base.update(kw)
    return ListingJobStart(**base)  # type: ignore[arg-type]


# ── DB 往返：两阶段生命周期 + 进行中可查 + 失败张留痕 ──────────────────────────


def test_two_phase_lifecycle_in_progress_queryable_and_partial_failure() -> None:
    async def _impl() -> None:
        hist, query = await _fresh_repos()

        # 阶段 1：入队建行 → 进行中单 DB 有行、可查（详情 + 列表都返回，非 404）
        await hist.start(_start())
        detail = await query.get_job(job_id="j1", user_id="u1")
        assert detail is not None
        assert detail.status == "生成中"
        assert detail.completed_at is None
        assert detail.images == ()
        assert detail.total_cost == Decimal("0")
        assert detail.input_keys == ("u1/a.png",)
        jobs = await query.list_jobs(user_id="u1", limit=10, offset=0)
        assert len(jobs) == 1
        assert jobs[0].status == "生成中"
        assert jobs[0].image_count == 0  # 进行中：尚无成功张
        assert jobs[0].first_image_key is None

        # owner 隔离：他人查进行中单 → None（路由映射 404）
        assert await query.get_job(job_id="j1", user_id="u2") is None
        assert await query.list_jobs(user_id="u2", limit=10, offset=0) == []

        # 阶段 2：逐张增量（1 成功白底 + 1 失败卖点，套图部分完成）
        await hist.add_images(
            "j1",
            (
                ListingJobImage(
                    image_key="aa.png", seed=1, cost=Decimal("0.4"),
                    status="成功", image_type="白底",
                ),
                ListingJobImage(
                    image_key="", seed=-1, cost=Decimal("0"),
                    status="失败", image_type="卖点",
                ),
            ),
        )
        detail = await query.get_job(job_id="j1", user_id="u1")
        assert detail is not None
        assert detail.status == "生成中"  # 终态尚未改
        by_type = {im.image_type: im for im in detail.images}
        assert by_type["白底"].status == "成功"
        assert by_type["卖点"].status == "失败"  # 失败张留痕（F5 恢复不丢）
        # 列表缩略/计数只算成功张（image_count 旧语义），首成功张作缩略
        jobs = await query.list_jobs(user_id="u1", limit=10, offset=0)
        assert jobs[0].image_count == 1
        assert jobs[0].first_image_key == "aa.png"

        # 阶段 3：终态改状态 + 补 completed_at + 失败原因入 job.error
        await hist.finalize(
            "j1", status="部分完成", total_cost=Decimal("0.4"), error="卖点：boom"
        )
        detail = await query.get_job(job_id="j1", user_id="u1")
        assert detail is not None
        assert detail.status == "部分完成"
        assert detail.completed_at is not None
        assert detail.total_cost == Decimal("0.4")
        assert detail.error is not None and "卖点" in detail.error
        assert len(detail.images) == 2  # 成功+失败张都在

    asyncio.run(_impl())


def test_add_images_empty_batch_is_noop() -> None:
    async def _impl() -> None:
        hist, query = await _fresh_repos()
        await hist.start(_start())
        await hist.add_images("j1", ())  # 无 no-op、不报错
        detail = await query.get_job(job_id="j1", user_id="u1")
        assert detail is not None and detail.images == ()

    asyncio.run(_impl())


def test_finalize_missing_row_fails_fast() -> None:
    async def _impl() -> None:
        hist, _ = await _fresh_repos()
        with pytest.raises(RuntimeError):  # start 未建行即终态 = 契约破坏
            await hist.finalize("nope", status="完成", total_cost=Decimal("0"), error=None)

    asyncio.run(_impl())


# ── 命令编排 + 时序：start→add_images→finalize 全部先于 TASK_COMPLETED ─────────


class _FakeHistory(ListingHistory):
    def __init__(self, log: list[tuple[str, object]]) -> None:
        self._log = log
        self.starts: list[ListingJobStart] = []
        self.batches: list[tuple[str, tuple[ListingJobImage, ...]]] = []
        self.finals: list[tuple[str, str, Decimal, str | None]] = []

    async def start(self, job: ListingJobStart) -> None:
        self.starts.append(job)
        self._log.append(("start", job.job_id))

    async def add_images(self, job_id: str, images: tuple[ListingJobImage, ...]) -> None:
        self.batches.append((job_id, images))
        self._log.append(("add_images", len(images)))

    async def finalize(
        self, job_id: str, *, status: str, total_cost: Decimal, error: str | None
    ) -> None:
        self.finals.append((job_id, status, total_cost, error))
        self._log.append(("finalize", status))


class _FakeEvents(EventPublisher):
    def __init__(self, log: list[tuple[str, object]]) -> None:
        self._log = log
        self.events: list[TaskEvent] = []

    async def publish(self, event: TaskEvent) -> None:
        self.events.append(event)
        self._log.append(("event", event.type))


class _FakeService:
    def __init__(self, result: ListingResult | None, exc: Exception | None = None) -> None:
        self._result = result
        self._exc = exc

    async def generate(self, **_kw: object) -> ListingResult:
        if self._exc is not None:
            raise self._exc
        assert self._result is not None
        return self._result


def _command(service: _FakeService, history: ListingHistory, events: EventPublisher):
    return ListingGenerationCommand(
        service=service,  # type: ignore[arg-type]
        events=events,
        history=history,
        user_id="u1",
        prompt="春节红",
        modifiers={"platform": "抖音电商"},
        images=(b"x",),
        upload_keys=("u1/a.png",),
        ratio="1:1",
        category="FOOD",
        n=None,
        plan={"白底": 1, "卖点": 1},  # 套图，Σ=2
    )


def test_command_two_phase_partial_persists_failure_and_orders_before_completed() -> None:
    log: list[tuple[str, object]] = []
    history = _FakeHistory(log)
    events = _FakeEvents(log)
    result = ListingResult(
        prompt="p",
        used_model=ModelName.GPT_IMAGE_2,
        images=(
            GeneratedImage(
                url="/img/aa.png", seed=7, latency_ms=10, cost=Decimal("0.4"), image_type="白底"
            ),
        ),
        total_cost=Decimal("0.4"),
        failures=(("卖点", "boom"),),  # 套图 1 张失败
    )
    cmd = _command(_FakeService(result), history, events)

    asyncio.run(cmd.run("j1"))

    # 阶段 1：入队即建行，计划张数=Σplan=2
    assert len(history.starts) == 1
    assert history.starts[0].n == 2
    assert history.starts[0].upload_keys == ("u1/a.png",)
    # 阶段 2：增量落图含失败张（成功白底 + 失败卖点）
    assert len(history.batches) == 1
    persisted = {im.image_type: im for im in history.batches[0][1]}
    assert persisted["白底"].status == "成功" and persisted["白底"].image_key == "aa.png"
    assert persisted["卖点"].status == "失败" and persisted["卖点"].image_key == ""
    # 阶段 3：终态=部分完成（成功 1 < 计划 2），失败原因入 error
    assert len(history.finals) == 1
    _, status, total_cost, error = history.finals[0]
    assert status == "部分完成"
    assert total_cost == Decimal("0.4")
    assert error is not None and "卖点" in error
    # 时序：start / add_images / finalize 全部先于 TASK_COMPLETED（详情必 200 不闪空）
    kinds = [k for k, _ in log]
    completed_at = log.index(("event", TaskEventType.TASK_COMPLETED))
    assert kinds.index("start") < kinds.index("event")  # 建行先于首个事件(TASK_STARTED)
    assert log.index(("add_images", 2)) < completed_at
    assert log.index(("finalize", "部分完成")) < completed_at


def test_command_full_success_status_complete() -> None:
    log: list[tuple[str, object]] = []
    history = _FakeHistory(log)
    result = ListingResult(
        prompt="p",
        used_model=ModelName.GPT_IMAGE_2,
        images=(
            GeneratedImage(
                url="/img/a.png", seed=1, latency_ms=1, cost=Decimal("0.4"), image_type="白底"
            ),
            GeneratedImage(
                url="/img/b.png", seed=2, latency_ms=1, cost=Decimal("0.4"), image_type="卖点"
            ),
        ),
        total_cost=Decimal("0.8"),
        failures=(),
    )
    cmd = _command(_FakeService(result), history, _FakeEvents(log))
    asyncio.run(cmd.run("j1"))
    assert history.finals[0][1] == "完成"  # 成功 2 >= 计划 2
    assert history.finals[0][3] is None  # 无失败原因


def test_command_failure_path_finalizes_failed_before_task_failed_no_images() -> None:
    log: list[tuple[str, object]] = []
    history = _FakeHistory(log)
    events = _FakeEvents(log)
    cmd = _command(_FakeService(None, exc=RuntimeError("上游 429")), history, events)

    with pytest.raises(RuntimeError):
        asyncio.run(cmd.run("j1"))

    # 建行仍发生（进行中单已可查），随后终态=失败、无增量落图
    assert len(history.starts) == 1
    assert history.batches == []
    assert len(history.finals) == 1
    _, status, total_cost, error = history.finals[0]
    assert status == "失败"
    assert total_cost == Decimal("0")
    assert error is not None and "上游 429" in error
    # 时序：finalize(失败) 先于 TASK_FAILED 事件
    assert log.index(("finalize", "失败")) < log.index(("event", TaskEventType.TASK_FAILED))


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(pytest.main([__file__, "-q"]))
