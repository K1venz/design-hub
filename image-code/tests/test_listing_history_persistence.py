"""两阶段落库单测（ISSUE-0047）：入队建行(生成中)→逐张增量(含失败张)→终态改状态；
进行中单可查、部分完成失败张留痕。DB 层走真实 SQLite 往返，命令层走 fakes 校验编排/时序。"""

import asyncio
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from design_hub.application.listing.commands import (
    CloneCommand,
    EditCommand,
    ListingGenerationCommand,
)
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
from design_hub.infrastructure.db.models import ListingJobRow
from design_hub.interface.api.asgi import STALE_JOB_REAP_AFTER
from design_hub.ports.events import EventPublisher
from design_hub.ports.listing_history import ListingHistory
from design_hub.ports.model_provider import ProviderTimeout


async def _fresh_stack() -> tuple[
    SqlAlchemyListingHistory,
    SqlAlchemyListingHistoryQuery,
    async_sessionmaker[AsyncSession],
]:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    sf = async_sessionmaker(engine, expire_on_commit=False)
    return SqlAlchemyListingHistory(sf), SqlAlchemyListingHistoryQuery(sf), sf


async def _fresh_repos() -> tuple[SqlAlchemyListingHistory, SqlAlchemyListingHistoryQuery]:
    hist, query, _ = await _fresh_stack()
    return hist, query


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
        assert detail.prompt == "春节红"
        assert "【全局真实性与细节质量约束】" not in detail.prompt
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


def test_category_persists_on_generate_and_is_null_on_edit() -> None:
    """品类档 DB 往返（ISSUE-0060）：generate/clone 落品类进 detail+summary；edit 单=NULL。"""
    async def _impl() -> None:
        hist, query = await _fresh_repos()
        await hist.start(_start(category="FASHION"))
        detail = await query.get_job(job_id="j1", user_id="u1")
        assert detail is not None and detail.category == "FASHION"
        summary = (await query.list_jobs(user_id="u1", limit=10, offset=0))[0]
        assert summary.category == "FASHION"
        # 编辑单不重述品类：ListingJobStart 默认 category=None → 落 NULL
        await hist.start(_start(job_id="e1", edit_mode="delta", parent_job_id="j1"))
        edit_detail = await query.get_job(job_id="e1", user_id="u1")
        assert edit_detail is not None and edit_detail.category is None

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
    def __init__(
        self, log: list[tuple[str, object]], *, add_images_error: Exception | None = None
    ) -> None:
        self._log = log
        self._add_images_error = add_images_error  # Finding A：注入落图段故障（DB 抖断等）
        self.starts: list[ListingJobStart] = []
        self.batches: list[tuple[str, tuple[ListingJobImage, ...]]] = []
        self.finals: list[tuple[str, str, Decimal, str | None]] = []

    async def start(self, job: ListingJobStart) -> None:
        self.starts.append(job)
        self._log.append(("start", job.job_id))

    async def add_images(self, job_id: str, images: tuple[ListingJobImage, ...]) -> None:
        if self._add_images_error is not None:
            self._log.append(("add_images_boom", len(images)))
            raise self._add_images_error
        self.batches.append((job_id, images))
        self._log.append(("add_images", len(images)))

    async def finalize(
        self, job_id: str, *, status: str, total_cost: Decimal, error: str | None
    ) -> None:
        self.finals.append((job_id, status, total_cost, error))
        self._log.append(("finalize", status))

    async def reap_stale(self, *, older_than: timedelta, error: str) -> int:
        return 0


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

    async def _run(self) -> ListingResult:
        if self._exc is not None:
            raise self._exc
        assert self._result is not None
        return self._result

    async def generate(self, **_kw: object) -> ListingResult:
        return await self._run()

    async def clone(self, **_kw: object) -> ListingResult:
        return await self._run()

    async def edit(self, **_kw: object) -> ListingResult:
        return await self._run()


class _BlockingService(_FakeService):
    def __init__(self) -> None:
        super().__init__(None)
        self.started = asyncio.Event()

    async def _run(self) -> ListingResult:
        self.started.set()
        await asyncio.Event().wait()
        raise AssertionError("unreachable")


def _single(image_key: str, url: str) -> ListingResult:
    """复刻/编辑用：单张成功结果（image_type 恒 None、failures 恒空）。"""
    return ListingResult(
        prompt="p",
        used_model=ModelName.GPT_IMAGE_2,
        images=(
            GeneratedImage(
                image_key=image_key,
                url=url,
                seed=3,
                latency_ms=5,
                cost=Decimal("0.4"),
            ),
        ),
        total_cost=Decimal("0.4"),
    )


def _clone_command(service: _FakeService, history: ListingHistory, events: EventPublisher):
    return CloneCommand(
        service=service,  # type: ignore[arg-type]
        events=events,
        history=history,
        user_id="u1",
        prompt="",
        modifiers={"platform": "抖音电商"},
        product_image=b"p",
        reference_images=(b"r",),
        upload_keys=("u1/p.png", "u1/r.png"),
        ratio="1:1",
        model=ModelName.GPT_IMAGE_2,
        category="FOOD",
        clone_mode="参考风格",
    )


def _edit_command(service: _FakeService, history: ListingHistory, events: EventPublisher):
    return EditCommand(
        service=service,  # type: ignore[arg-type]
        events=events,
        history=history,
        user_id="u1",
        prompt="把背景换成米色",
        modifiers={"platform": "抖音电商"},
        source_image=b"s",
        anchor_images=(b"a",),
        anchor_keys=("u1/a.png",),
        parent_job_id="parent1",
        source_image_key="src.png",
        ratio="1:1",
        model=ModelName.GPT_IMAGE_2,
        edit_mode="delta",
    )


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
        model=ModelName.GPT_IMAGE_2,
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
                image_key="aa.png",
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
    assert history.starts[0].category == "FOOD"  # 品类进快照（ISSUE-0060）
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
                image_key="a.png",
                url="/img/a.png", seed=1, latency_ms=1, cost=Decimal("0.4"), image_type="白底"
            ),
            GeneratedImage(
                image_key="b.png",
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


def test_command_persists_explicit_image_key_instead_of_parsing_display_url() -> None:
    history = _FakeHistory([])
    long_external_url = "https://upstream.example/result/" + ("signed-segment-" * 20)
    result = ListingResult(
        prompt="p",
        used_model=ModelName.GPT_IMAGE_2_4K,
        images=(
            GeneratedImage(
                image_key="owned.png",
                url=long_external_url,
                seed=1,
                latency_ms=1,
                cost=Decimal("0.18"),
            ),
        ),
        total_cost=Decimal("0.18"),
    )

    asyncio.run(_clone_command(_FakeService(result), history, _FakeEvents([])).run("j1"))

    persisted = history.batches[0][1][0]
    assert persisted.image_key == "owned.png"


def test_command_failure_path_finalizes_failed_before_task_failed_no_images() -> None:
    log: list[tuple[str, object]] = []
    history = _FakeHistory(log)
    events = _FakeEvents(log)
    # 上游持久 5xx（apinebula new-api 渠道故障）穷尽重试后上抛（ISSUE-0055 场景）
    raw = "gpt-image-2 500: prepare chat requirements error (traceid=abc123)"
    cmd = _command(_FakeService(None, exc=ProviderTimeout(raw)), history, events)

    with pytest.raises(ProviderTimeout):
        asyncio.run(cmd.run("j1"))

    # 建行仍发生（进行中单已可查），随后终态=失败、无增量落图
    assert len(history.starts) == 1
    assert history.batches == []
    assert len(history.finals) == 1
    _, status, total_cost, error = history.finals[0]
    assert status == "失败"
    assert total_cost == Decimal("0")
    # 用户面=人话 + 出图段未扣费；原始 500/traceid/模型名绝不泄漏（ISSUE-0055 (ii)）
    assert error is not None
    assert "图像服务临时繁忙" in error and "本单未扣费" in error
    assert "500" not in error and "traceid" not in error and "gpt-image-2" not in error
    # 时序：finalize(失败) 先于 TASK_FAILED 事件
    assert log.index(("finalize", "失败")) < log.index(("event", TaskEventType.TASK_FAILED))


def test_command_cancellation_finalizes_failed_before_reraising() -> None:
    async def _impl() -> None:
        log: list[tuple[str, object]] = []
        history = _FakeHistory(log)
        events = _FakeEvents(log)
        service = _BlockingService()
        cmd = _command(service, history, events)
        task = asyncio.create_task(cmd.run("j-cancelled"))
        await service.started.wait()

        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task

        assert history.finals[0][1] == "失败"
        assert log.index(("finalize", "失败")) < log.index(
            ("event", TaskEventType.TASK_FAILED)
        )

    asyncio.run(_impl())


# ── 复刻/编辑命令编排 + 时序（单张流：start→add_images→finalize 先于 TASK_COMPLETED）──


def test_clone_command_orchestration_and_ordering() -> None:
    log: list[tuple[str, object]] = []
    history = _FakeHistory(log)
    events = _FakeEvents(log)
    cmd = _clone_command(_FakeService(_single("c.png", "/img/c.png")), history, events)

    asyncio.run(cmd.run("jc"))

    # 建行快照：单张（n=1）+ 双角色（产品前·参考后）+ 复刻档
    assert len(history.starts) == 1
    snap = history.starts[0]
    assert snap.n == 1
    assert snap.clone_mode == "参考风格"
    assert snap.input_roles == ("product", "reference")
    assert snap.upload_keys == ("u1/p.png", "u1/r.png")
    # 落图：单张成功（image_type=None）、终态=完成、无失败原因
    assert len(history.batches) == 1
    (persisted,) = history.batches[0][1]
    assert persisted.status == "成功" and persisted.image_key == "c.png"
    assert persisted.image_type is None
    assert history.finals[0][1] == "完成" and history.finals[0][3] is None
    # 时序：start / add_images / finalize 全部先于 TASK_COMPLETED
    completed_at = log.index(("event", TaskEventType.TASK_COMPLETED))
    assert [k for k, _ in log].index("start") < completed_at
    assert log.index(("add_images", 1)) < completed_at
    assert log.index(("finalize", "完成")) < completed_at


def test_edit_command_orchestration_and_ordering() -> None:
    log: list[tuple[str, object]] = []
    history = _FakeHistory(log)
    events = _FakeEvents(log)
    cmd = _edit_command(_FakeService(_single("e.png", "/img/e.png")), history, events)

    asyncio.run(cmd.run("je"))

    # 建行快照：迭代链回显（parent/source/edit_mode）+ 链根锚 role=product
    assert len(history.starts) == 1
    snap = history.starts[0]
    assert snap.n == 1
    assert snap.parent_job_id == "parent1"
    assert snap.source_image_key == "src.png"
    assert snap.edit_mode == "delta"
    assert snap.input_roles == ("product",)
    assert snap.upload_keys == ("u1/a.png",)
    # 落图：单张成功、终态=完成；时序先于 TASK_COMPLETED
    (persisted,) = history.batches[0][1]
    assert persisted.status == "成功" and persisted.image_key == "e.png"
    assert history.finals[0][1] == "完成"
    completed_at = log.index(("event", TaskEventType.TASK_COMPLETED))
    assert log.index(("add_images", 1)) < completed_at
    assert log.index(("finalize", "完成")) < completed_at


# ── Finding A：出图成功后的落库/发事件段抛错 → fail-closed 兜底（终态失败，非僵尸单）──


def test_command_persist_failure_fails_closed_to_failed() -> None:
    log: list[tuple[str, object]] = []
    boom = RuntimeError("DB 抖断（add_images）")
    history = _FakeHistory(log, add_images_error=boom)  # 出图成功、落图段抛错
    events = _FakeEvents(log)
    result = ListingResult(
        prompt="p",
        used_model=ModelName.GPT_IMAGE_2,
        images=(
            GeneratedImage(
                image_key="aa.png",
                url="/img/aa.png", seed=7, latency_ms=10, cost=Decimal("0.4"), image_type="白底"
            ),
        ),
        total_cost=Decimal("0.4"),
        failures=(("卖点", "boom"),),
    )
    cmd = _command(_FakeService(result), history, events)

    with pytest.raises(RuntimeError):
        asyncio.run(cmd.run("j1"))

    # generate 成功后落图段确曾进入（add_images 抛错），随后 fail-closed 终态=失败
    assert ("add_images_boom", 2) in [(k, v) for k, v in log]
    assert history.batches == []  # 成功批未落
    assert len(history.finals) == 1
    _, status, total_cost, error = history.finals[0]
    assert status == "失败"
    assert total_cost == Decimal("0")
    # 落库段失败：用户面人话、DB 内部错不泄漏；出图已成功计费 → 不宣称「未扣费」(refunded=False)
    assert error is not None
    assert "DB 抖断" not in error and "add_images" not in error
    assert "本单未扣费" not in error
    # 时序：finalize(失败) 先于 TASK_FAILED；且绝不误发 TASK_COMPLETED（非成功、非僵尸）
    assert log.index(("finalize", "失败")) < log.index(("event", TaskEventType.TASK_FAILED))
    assert ("event", TaskEventType.TASK_COMPLETED) not in log


# ── Finding B：启动 reaper 把进程崩/部署撞出图中留下的「生成中」僵尸行扫成失败 ──


async def _backdate(
    sf: async_sessionmaker[AsyncSession], job_id: str, created_at: datetime
) -> None:
    async with sf() as session:
        await session.execute(
            update(ListingJobRow).where(ListingJobRow.id == job_id).values(created_at=created_at)
        )
        await session.commit()


def test_reaper_sweeps_stale_in_progress_only() -> None:
    """僵尸单场景（start 后不 finalize 的持久态）+ 启动 reaper 扫成失败；新鲜/终态单不误伤。"""

    async def _impl() -> None:
        hist, query, sf = await _fresh_stack()
        old = datetime.now(UTC) - timedelta(hours=1)
        # 僵尸：start 后无 finalize（进程崩），且超龄
        await hist.start(_start(job_id="stale", n=1))
        await _backdate(sf, "stale", old)
        # 30 分钟：长 4K 批次仍可能在飞，45 分钟阈值下绝不误杀。
        await hist.start(_start(job_id="long-running", n=1))
        await _backdate(
            sf, "long-running", datetime.now(UTC) - timedelta(minutes=30)
        )
        # 终态：完成（即便超龄也不该被碰）
        await hist.start(_start(job_id="done", n=1))
        await _backdate(sf, "done", old)
        await hist.finalize("done", status="完成", total_cost=Decimal("0.4"), error=None)

        # 扫前：僵尸单持久态=生成中、可查（SSE 会永久转圈、霸占最近一单）
        pre = await query.get_job(job_id="stale", user_id="u1")
        assert pre is not None and pre.status == "生成中" and pre.completed_at is None

        reaped = await hist.reap_stale(
            older_than=STALE_JOB_REAP_AFTER, error="进程重启中断/超时兜底"
        )
        assert reaped == 1  # 只扫僵尸那一行

        stale = await query.get_job(job_id="stale", user_id="u1")
        assert stale is not None and stale.status == "失败"
        assert stale.error is not None and "超时兜底" in stale.error
        assert stale.completed_at is not None  # 补终态时间，SSE/前端不再转圈
        long_running = await query.get_job(job_id="long-running", user_id="u1")
        assert long_running is not None and long_running.status == "生成中"
        done = await query.get_job(job_id="done", user_id="u1")
        assert done is not None and done.status == "完成"  # 终态不改

    asyncio.run(_impl())


def test_reaper_noop_when_nothing_stale() -> None:
    async def _impl() -> None:
        hist, _, _ = await _fresh_stack()
        await hist.start(_start(job_id="fresh", n=1))  # 刚建、未超龄
        assert await hist.reap_stale(older_than=STALE_JOB_REAP_AFTER, error="x") == 0

    asyncio.run(_impl())


def test_startup_reaper_threshold_covers_maximum_4k_batch() -> None:
    assert STALE_JOB_REAP_AFTER >= timedelta(minutes=45)


# ── resolve_edit_source：失败哨兵（image_key=''）不可被当编辑源解析（Q-δ 状态闸）──


def test_resolve_edit_source_ignores_failed_sentinel() -> None:
    async def _impl() -> None:
        hist, query, _ = await _fresh_stack()
        # 根单（无 parent）：1 成功白底 + 1 失败卖点哨兵（image_key=''），产品输入 role=None
        await hist.start(_start(job_id="root", n=1))
        await hist.add_images(
            "root",
            (
                ListingJobImage(
                    image_key="ok.png", seed=1, cost=Decimal("0.4"),
                    status="成功", image_type="白底",
                ),
                ListingJobImage(
                    image_key="", seed=-1, cost=Decimal("0"),
                    status="失败", image_type="卖点",
                ),
            ),
        )
        await hist.finalize(
            "root", status="部分完成", total_cost=Decimal("0.4"), error="卖点：boom"
        )

        # 正控：成功张可反解为编辑源（链根产品锚回显）
        src = await query.resolve_edit_source(source_image_key="ok.png", user_id="u1")
        assert src is not None
        assert src.parent_job_id == "root"
        assert src.root_product_upload_keys == ("u1/a.png",)
        # 反控：失败哨兵（image_key=''）绝不可被解析为编辑源（否则空 key 当源图链根）
        assert await query.resolve_edit_source(source_image_key="", user_id="u1") is None

    asyncio.run(_impl())


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(pytest.main([__file__, "-q"]))
