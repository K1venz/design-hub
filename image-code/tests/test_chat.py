"""「帮我设计」方案 C 对话编排单测（固化原手工 E2E，ISSUE-0048 chat 测试债）。

覆盖：ChatOrchestrator 事件序 / 费用闸（cost_confirm 暂停不出图）/ confirm 启 job + job_event
转发 / confirm_token 一次性·跨用户·cancel·过期 / 会话级出图闸 / 占位 ratio→转澄清 /
澄清轮无工具；ListingJobLauncher.validate 纯校验；InMemorySessionStore token 语义。

真出图链走 mock 图像 provider（零成本）+ 真 InMemoryEventBus/InProcessTaskQueue + sqlite 历史。
文本 LLM 用确定性 Stub（真 provider 的流式/工具解析在 test_text_llm_adapter.py 覆盖）。
"""

import asyncio
from collections.abc import AsyncIterator
from dataclasses import dataclass
from decimal import Decimal

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from design_hub.application.chat.orchestrator import ChatOrchestrator
from design_hub.application.chat.session_store import InMemorySessionStore
from design_hub.application.cost.budget import BudgetPolicy
from design_hub.application.cost.guard import CostGuard
from design_hub.application.listing.job_launcher import ListingJobLauncher
from design_hub.application.listing.listing_service import ListingGenerationService
from design_hub.application.listing.prompt_composer import (
    CategoryCardRegistry,
    CloneModeRegistry,
    EditModeRegistry,
    ImageTypeRegistry,
    PromptModifierRegistry,
)
from design_hub.application.listing.requests import (
    CloneRequest,
    EditRequest,
    ListingGenerateRequest,
)
from design_hub.application.listing.upload_service import UploadService
from design_hub.application.rate_limit import UserRateLimiter
from design_hub.application.registry import ProviderRegistry
from design_hub.composition import build_mock_registry
from design_hub.domain.enums import ModelName, Role
from design_hub.domain.errors import NotFoundError
from design_hub.domain.models import AuthUser, BudgetSnapshot
from design_hub.infrastructure.db.base import Base
from design_hub.infrastructure.db.listing_history_repo import SqlAlchemyListingHistory
from design_hub.infrastructure.db.listing_query_repo import SqlAlchemyListingHistoryQuery
from design_hub.infrastructure.events.memory import InMemoryEventBus
from design_hub.infrastructure.queue.in_process import InProcessTaskQueue
from design_hub.infrastructure.storage.local import LocalImageStore
from design_hub.infrastructure.storage.local_upload import LocalUploadStore
from design_hub.ports.ledger import LedgerRepository
from design_hub.ports.text_llm import (
    ChatMessage,
    LLMChunk,
    TextChunk,
    TextLLMPort,
    ToolCall,
    ToolCallChunk,
    ToolSpec,
)

USER = AuthUser(user_id="u1", name="测试", role=Role.DESIGNER)
OTHER = AuthUser(user_id="u2", name="他人", role=Role.DESIGNER)
_PNG = b"\x89PNG\r\n\x1a\n" + b"0" * 64
_PLAN = {"白底": 1, "场景": 2, "卖点": 2}


class _FakeLedger(LedgerRepository):
    async def snapshot(self, user_id: str) -> BudgetSnapshot:
        return BudgetSnapshot(Decimal(0), Decimal(1000), Decimal(0), Decimal(100000))

    async def reserve(self, user_id: str, amount: Decimal) -> None: ...

    async def rollback(self, user_id: str, amount: Decimal) -> None: ...


class StubTextLLM(TextLLMPort):
    """确定性文本 LLM：每次带工具的调用取下一条脚本；收尾轮（无工具）产固定收尾语。"""

    is_live = False

    def __init__(self, *turns: tuple[str, tuple[ToolCall, ...]]) -> None:
        self._turns = list(turns)
        self._i = 0

    async def complete(
        self, *, messages: list[ChatMessage], tools: list[ToolSpec]
    ) -> AsyncIterator[LLMChunk]:
        if not tools:  # 收尾轮
            yield TextChunk("已完成，可在结果区查看。")
            return
        text, calls = self._turns[min(self._i, len(self._turns) - 1)]
        self._i += 1
        if text:
            yield TextChunk(text)
        if calls:
            yield ToolCallChunk(calls)


def _gen_tc(
    uid: str, *, ratio: str = "1:1", n: int | None = 5, plan: dict | None = None
) -> tuple[ToolCall, ...]:
    args: dict = {"upload_ids": [uid], "prompt": "花生", "ratio": ratio, "category": "FOOD"}
    if plan is not None:
        args["plan"] = plan
    else:
        args["n"] = n
    return (ToolCall(id="c1", name="generate", arguments=args),)


@dataclass
class Infra:
    launcher: ListingJobLauncher
    uploads: UploadService
    registry: ProviderRegistry
    events: InMemoryEventBus
    sessions: InMemorySessionStore
    max_session_jobs: int

    def orch(self, text_llm: TextLLMPort) -> ChatOrchestrator:
        return ChatOrchestrator(
            text_llm=text_llm, launcher=self.launcher, event_stream=self.events,
            registry=self.registry, sessions=self.sessions, max_session_jobs=self.max_session_jobs,
        )


async def _infra(tmp: str, *, max_session_jobs: int = 5) -> Infra:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    sf = async_sessionmaker(engine, expire_on_commit=False)
    registry = build_mock_registry()
    service = ListingGenerationService(
        registry=registry, guard=CostGuard(ledger=_FakeLedger(), policy=BudgetPolicy()),
        modifier_registry=PromptModifierRegistry(), card_registry=CategoryCardRegistry(),
        type_registry=ImageTypeRegistry(), clone_registry=CloneModeRegistry(),
        edit_registry=EditModeRegistry(), concurrency=3,
    )
    events = InMemoryEventBus()
    uploads = UploadService(store=LocalUploadStore(tmp))
    launcher = ListingJobLauncher(
        service=service, uploads=uploads, rate_limiter=UserRateLimiter(), events=events,
        history=SqlAlchemyListingHistory(sf), queue=InProcessTaskQueue(),
        query=SqlAlchemyListingHistoryQuery(sf), image_store=LocalImageStore(tmp),
    )
    return Infra(launcher, uploads, registry, events, InMemorySessionStore(), max_session_jobs)


async def _drain(agen: AsyncIterator) -> list[tuple[str, dict]]:
    return [(e.type, e.data) async for e in agen]


async def _stage(inf: Infra, user: AuthUser = USER) -> str:
    return await inf.uploads.save(data=_PNG, content_type="image/png", user_id=user.user_id)


def _first(events: list[tuple[str, dict]], type_: str) -> dict:
    return next(d for t, d in events if t == type_)


# ── ChatOrchestrator 事件序 + 费用闸 ──────────────────────────────────────────


def test_valid_tool_call_reaches_cost_confirm_without_generating(tmp_path) -> None:
    async def _impl() -> None:
        inf = await _infra(str(tmp_path))
        uid = await _stage(inf)
        orch = inf.orch(StubTextLLM(("好的，我来帮你出一套图。", _gen_tc(uid, plan=_PLAN))))
        ev = await _drain(orch.handle_message(USER, None, "给我的花生出一套5张", [uid]))
        types = [t for t, _ in ev]
        assert types == [
            "session", "assistant_delta", "step", "tool_call", "cost_confirm", "assistant_end",
        ]
        assert _first(ev, "tool_call")["tool"] == "generate"
        cc = _first(ev, "cost_confirm")
        assert cc["count"] == 5
        unit = inf.registry.get(ModelName.GPT_IMAGE_2).unit_cost
        assert cc["estimate_cny"] == str(unit * 5)  # 与工作台同源（#884③）
        assert ev[-1] == ("assistant_end", {"status": "awaiting_confirm"})
        # 费用闸：确认前会话 job_count=0（未出图、未扣费）
        session = inf.sessions.get(_first(ev, "session")["session_id"], USER.user_id)
        assert session is not None and session.job_count == 0

    asyncio.run(_impl())


def test_confirm_launches_job_and_forwards_job_events(tmp_path) -> None:
    async def _impl() -> None:
        inf = await _infra(str(tmp_path))
        uid = await _stage(inf)
        orch = inf.orch(StubTextLLM(("", _gen_tc(uid, plan=_PLAN))))
        msg = await _drain(orch.handle_message(USER, None, "出一套", [uid]))
        sid = _first(msg, "session")["session_id"]
        tok = _first(msg, "cost_confirm")["confirm_token"]
        conf = await _drain(orch.handle_confirm(USER, sid, tok, "confirm"))
        types = [t for t, _ in conf]
        assert "job_started" in types
        assert _first(conf, "job_started")["plan"] == _PLAN
        je = [d["type"] for t, d in conf if t == "job_event"]
        assert "task_started" in je
        assert je.count("image_generated") == 5
        assert "task_completed" in je
        assert conf[-1] == ("assistant_end", {"status": "complete"})

    asyncio.run(_impl())


def test_confirm_token_is_one_time(tmp_path) -> None:
    async def _impl() -> None:
        inf = await _infra(str(tmp_path))
        uid = await _stage(inf)
        orch = inf.orch(StubTextLLM(("", _gen_tc(uid, n=1))))
        msg = await _drain(orch.handle_message(USER, None, "出一张", [uid]))
        sid = _first(msg, "session")["session_id"]
        tok = _first(msg, "cost_confirm")["confirm_token"]
        await _drain(orch.handle_confirm(USER, sid, tok, "confirm"))
        again = await _drain(orch.handle_confirm(USER, sid, tok, "confirm"))
        assert any(t == "error" and d["code"] == "invalid_confirm_token" for t, d in again)

    asyncio.run(_impl())


def test_cross_user_cannot_touch_session(tmp_path) -> None:
    async def _impl() -> None:
        inf = await _infra(str(tmp_path))
        uid = await _stage(inf)
        orch = inf.orch(StubTextLLM(("", _gen_tc(uid, n=1))))
        msg = await _drain(orch.handle_message(USER, None, "出一张", [uid]))
        sid = _first(msg, "session")["session_id"]
        cross = await _drain(orch.handle_message(OTHER, sid, "偷看", []))
        assert any(t == "error" and d["code"] == "bad_request" for t, d in cross)

    asyncio.run(_impl())


def test_cancel_invalidates_token_no_job(tmp_path) -> None:
    async def _impl() -> None:
        inf = await _infra(str(tmp_path))
        uid = await _stage(inf)
        orch = inf.orch(StubTextLLM(("", _gen_tc(uid, n=1))))
        msg = await _drain(orch.handle_message(USER, None, "出一张", [uid]))
        sid = _first(msg, "session")["session_id"]
        tok = _first(msg, "cost_confirm")["confirm_token"]
        canc = await _drain(orch.handle_confirm(USER, sid, tok, "cancel"))
        assert not any(t == "job_started" for t, _ in canc)
        assert canc[-1] == ("assistant_end", {"status": "complete"})
        after = await _drain(orch.handle_confirm(USER, sid, tok, "confirm"))
        assert any(t == "error" and d["code"] == "invalid_confirm_token" for t, d in after)

    asyncio.run(_impl())


def test_session_job_limit_blocks_second_confirm(tmp_path) -> None:
    async def _impl() -> None:
        inf = await _infra(str(tmp_path), max_session_jobs=1)
        uid = await _stage(inf)
        orch = inf.orch(StubTextLLM(("", _gen_tc(uid, n=1))))
        m1 = await _drain(orch.handle_message(USER, None, "出一张", [uid]))
        sid = _first(m1, "session")["session_id"]
        tok1 = _first(m1, "cost_confirm")["confirm_token"]
        c1 = await _drain(orch.handle_confirm(USER, sid, tok1, "confirm"))
        assert any(t == "job_started" for t, _ in c1)
        m2 = await _drain(orch.handle_message(USER, sid, "再出一张", [uid]))
        tok2 = _first(m2, "cost_confirm")["confirm_token"]
        c2 = await _drain(orch.handle_confirm(USER, sid, tok2, "confirm"))
        assert any(t == "error" and d["code"] == "session_job_limit" for t, d in c2)
        assert not any(t == "job_started" for t, _ in c2)

    asyncio.run(_impl())


def test_placeholder_ratio_becomes_clarification_not_paid_error(tmp_path) -> None:
    async def _impl() -> None:
        inf = await _infra(str(tmp_path))
        uid = await _stage(inf)
        # 真 LLM 偶把「请问你要什么比例?」填进 ratio → 进费用闸前拦下转澄清
        orch = inf.orch(StubTextLLM(("好的", _gen_tc(uid, ratio="请问你要什么比例?", n=1))))
        ev = await _drain(orch.handle_message(USER, None, "出图", [uid]))
        types = [t for t, _ in ev]
        assert "cost_confirm" not in types
        assert "tool_call" not in types
        assert any(t == "assistant_delta" for t in types)
        assert ev[-1] == ("assistant_end", {"status": "complete"})

    asyncio.run(_impl())


def test_clarify_turn_without_tool_completes(tmp_path) -> None:
    async def _impl() -> None:
        inf = await _infra(str(tmp_path))
        orch = inf.orch(StubTextLLM(("请描述你想要的设计，并上传产品图。", ())))
        ev = await _drain(orch.handle_message(USER, None, "你好", []))
        types = [t for t, _ in ev]
        assert "cost_confirm" not in types and "tool_call" not in types
        assert any(t == "assistant_delta" for t in types)
        assert ev[-1] == ("assistant_end", {"status": "complete"})

    asyncio.run(_impl())


# ── ListingJobLauncher.validate 纯校验（#884⑤ 与出图同一校验源）─────────────────


def test_validate_rejects_bad_ratio(tmp_path) -> None:
    async def _impl() -> None:
        inf = await _infra(str(tmp_path))
        uid = await _stage(inf)
        req = ListingGenerateRequest(upload_ids=[uid], prompt="p", ratio="2:3", n=1)
        with pytest.raises(ValueError):
            inf.launcher.validate(USER, req)

    asyncio.run(_impl())


def test_validate_rejects_non_owned_upload(tmp_path) -> None:
    async def _impl() -> None:
        inf = await _infra(str(tmp_path))
        req = ListingGenerateRequest(
            upload_ids=["deadbeef0000/x.png"], prompt="p", ratio="1:1", n=1
        )
        with pytest.raises(NotFoundError):
            inf.launcher.validate(USER, req)

    asyncio.run(_impl())


def test_validate_clone_requires_one_product(tmp_path) -> None:
    async def _impl() -> None:
        inf = await _infra(str(tmp_path))
        req = CloneRequest(
            product_upload_ids=[], reference_upload_ids=["a"], clone_mode="参考风格", ratio="1:1"
        )
        with pytest.raises(ValueError):
            inf.launcher.validate(USER, req)

    asyncio.run(_impl())


def test_validate_edit_delta_rejects_ratio(tmp_path) -> None:
    async def _impl() -> None:
        inf = await _infra(str(tmp_path))
        req = EditRequest(source_image_key="k", prompt="改暖色", edit_mode="delta", ratio="1:1")
        with pytest.raises(ValueError):
            inf.launcher.validate(USER, req)

    asyncio.run(_impl())


# ── InMemorySessionStore：confirm_token 一次性 / 绑 user / 过期 / cancel ─────────


def _req() -> ListingGenerateRequest:
    return ListingGenerateRequest(upload_ids=["a"], prompt="p", ratio="1:1", n=1)


def test_session_owner_isolation() -> None:
    s = InMemorySessionStore()
    sess = s.create("u1")
    assert s.get(sess.session_id, "u1") is sess
    assert s.get(sess.session_id, "u2") is None
    assert s.get("nope", "u1") is None


def test_take_pending_one_time_and_mismatch_preserves() -> None:
    s = InMemorySessionStore()
    sess = s.create("u1")
    p = s.new_pending(sess, tool="generate", req=_req(), count=1, estimate=Decimal("0.4"))
    assert s.take_pending(sess, "wrong") is None  # 不匹配不消费
    assert s.take_pending(sess, p.confirm_token) is p  # 真 token 仍在
    assert s.take_pending(sess, p.confirm_token) is None  # 一次性，二次拒


def test_take_pending_expired() -> None:
    s = InMemorySessionStore(ttl_seconds=-1.0)  # 立即过期
    sess = s.create("u1")
    p = s.new_pending(sess, tool="generate", req=_req(), count=1, estimate=Decimal("0.4"))
    assert s.take_pending(sess, p.confirm_token) is None  # 匹配但过期
    assert sess.pending is None  # 且已消费


def test_cancel_pending() -> None:
    s = InMemorySessionStore()
    sess = s.create("u1")
    p = s.new_pending(sess, tool="generate", req=_req(), count=1, estimate=Decimal("0.4"))
    s.cancel_pending(sess)
    assert sess.pending is None
    assert s.take_pending(sess, p.confirm_token) is None
