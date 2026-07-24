"""「帮我设计」方案 C 对话编排 + 持久化单测（ISSUE-0048 chat 测试债 + ISSUE-0051 持久化）。

覆盖：ChatOrchestrator 事件序 / 费用闸(cost_confirm 暂停不出图) / confirm 启 job+job_event 转发 /
confirm_token 一次性·跨用户·cancel·过期 / 会话级闸(DB 派生) / 占位 ratio→转澄清 / 澄清轮无工具;
ListingJobLauncher.validate 纯校验; PendingStore token 语义; ChatSessionRepository 持久化(刷新
不丢/owner 404/CASCADE 删/job_count) + 转录落库(user 消息+assistant 答复+job_id,过程态不落)。

真出图链走 mock 图像 provider(零成本)+ 真 InMemoryEventBus/InProcessTaskQueue + sqlite。
文本 LLM 用确定性 Stub(真 provider 流式/工具解析在 test_text_llm_adapter.py 覆盖)。
"""

import asyncio
from collections.abc import AsyncIterator
from dataclasses import dataclass
from decimal import Decimal
from io import BytesIO

import pytest
from PIL import Image
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from design_hub.application.chat.orchestrator import ChatOrchestrator
from design_hub.application.chat.pending_store import PendingStore
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
from design_hub.infrastructure.db.chat_repo import SqlAlchemyChatSessionRepository
from design_hub.infrastructure.db.listing_history_repo import SqlAlchemyListingHistory
from design_hub.infrastructure.db.listing_query_repo import SqlAlchemyListingHistoryQuery
from design_hub.infrastructure.events.memory import InMemoryEventBus
from design_hub.infrastructure.providers.mock_text import MockTextLLMProvider
from design_hub.infrastructure.queue.in_process import InProcessTaskQueue
from design_hub.infrastructure.storage.local import LocalImageStore, LocalMediaUrlSigner
from design_hub.infrastructure.storage.local_upload import LocalUploadStore
from design_hub.ports.chat_repository import ChatSessionRepository
from design_hub.ports.ledger import LedgerRepository
from design_hub.ports.model_config_repository import ModelConfigRecord, ModelConfigRepository
from design_hub.ports.text_llm import (
    ChatMessage,
    LLMChunk,
    TextChunk,
    TextLLMPort,
    ToolCall,
    ToolCallChunk,
    ToolSpec,
)
from design_hub.ports.upload_store import UploadReadError, UploadStore, upload_ns

USER = AuthUser(user_id="u1", name="测试", role=Role.DESIGNER)
OTHER = AuthUser(user_id="u2", name="他人", role=Role.DESIGNER)
_PNG = b"\x89PNG\r\n\x1a\n" + b"0" * 64
_PLAN = {"白底": 1, "场景": 2, "卖点": 2}


class _FakeLedger(LedgerRepository):
    async def snapshot(self, user_id: str) -> BudgetSnapshot:
        return BudgetSnapshot(Decimal(0), Decimal(1000), Decimal(0), Decimal(100000))

    async def reserve(self, user_id: str, amount: Decimal) -> None: ...

    async def rollback(self, user_id: str, amount: Decimal) -> None: ...


class _FakeModelConfig(ModelConfigRepository):
    def __init__(self) -> None:
        self._c = [
            ModelConfigRecord("gpt-image-2", Decimal("0.40"), enabled=True, extra={}),
            ModelConfigRecord("seedream-5", Decimal("0.20"), enabled=False, extra={}),
        ]

    async def list_all(self) -> list[ModelConfigRecord]:
        return list(self._c)

    async def get(self, name: str) -> ModelConfigRecord | None:
        return next((c for c in self._c if c.name == name), None)

    async def update(self, name, **kw):  # type: ignore[no-untyped-def]
        raise NotImplementedError

    async def create(self, record):  # type: ignore[no-untyped-def]
        raise NotImplementedError

    async def delete(self, name) -> None:  # type: ignore[no-untyped-def]
        raise NotImplementedError

    async def set_default(self, name):  # type: ignore[no-untyped-def]
        raise NotImplementedError

    async def seed_defaults(self, defaults) -> None:  # type: ignore[no-untyped-def]
        raise NotImplementedError


class StubTextLLM(TextLLMPort):
    """确定性文本 LLM：每次带工具的调用取下一条脚本；收尾轮(无工具)产固定收尾语。"""

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


class CapturingTextLLM(TextLLMPort):
    is_live = False

    def __init__(self) -> None:
        self.messages: list[ChatMessage] = []

    async def complete(
        self, *, messages: list[ChatMessage], tools: list[ToolSpec]
    ) -> AsyncIterator[LLMChunk]:
        self.messages = messages
        yield TextChunk("请确认设计要求。")


class _ReadFailureUploadStore(UploadStore):
    async def save(self, data: bytes, *, content_type: str, user_id: str) -> str:
        raise NotImplementedError

    async def load(self, upload_id: str) -> tuple[bytes, str]:
        raise UploadReadError(f"读取上传图失败：{upload_id}")


def _image_bytes(width: int, height: int) -> bytes:
    out = BytesIO()
    Image.new("RGB", (width, height)).save(out, format="PNG")
    return out.getvalue()


def _gen_tc(
    uid: str,
    *,
    ratio: str = "1:1",
    n: int | None = 5,
    plan: dict | None = None,
    prompt: str = "花生",
) -> tuple[ToolCall, ...]:
    args: dict = {"upload_ids": [uid], "prompt": prompt, "ratio": ratio}
    if plan is not None:
        args["plan"] = plan
    else:
        args["n"] = n
    return (ToolCall(id="c1", name="generate", arguments=args),)


def test_chat_generate_converts_to_category_free_listing_request() -> None:
    req = ChatOrchestrator._parse_req(
        "generate",
        {
            "upload_ids": ["u"],
            "prompt": "主体居中，柔和棚拍光，保留原图 Logo",
            "ratio": "1:1",
            "n": 1,
        },
    )
    assert isinstance(req, ListingGenerateRequest)
    assert req.category is None


def test_chat_generate_rejects_category_argument() -> None:
    with pytest.raises(ValueError):
        ChatOrchestrator._parse_req(
            "generate",
            {
                "upload_ids": ["u"],
                "prompt": "极简海报",
                "ratio": "1:1",
                "n": 1,
                "category": "FOOD",
            },
        )


def test_logo_request_uses_enhanced_prompt_without_category_clarification(tmp_path) -> None:
    async def _impl() -> None:
        inf = await _infra(str(tmp_path))
        uid = await _stage(inf)
        enhanced = (
            "以用户上传图为主体，设计简洁现代的 Logo 视觉；保持原图已有文字与标识不变，"
            "主体居中，留白充足，使用清晰矢量感边缘，不新增品牌名或宣传文案。"
        )
        orch = inf.orch(
            StubTextLLM(("正在完善设计要求", _gen_tc(uid, n=1, prompt=enhanced)))
        )

        events = await _drain(
            orch.handle_message(USER, None, "帮我做一个简洁现代的 Logo", [uid])
        )

        confirm = _first(events, "cost_confirm")
        assert confirm["args"]["prompt"] == enhanced
        assert "category" not in confirm["args"]
        assert not any(
            "品类" in data.get("text", "")
            for event_type, data in events
            if event_type == "assistant_delta"
        )

    asyncio.run(_impl())


@dataclass
class Infra:
    launcher: ListingJobLauncher
    uploads: UploadService
    registry: ProviderRegistry
    events: InMemoryEventBus
    chat_repo: ChatSessionRepository
    pending: PendingStore
    query: SqlAlchemyListingHistoryQuery
    ledger: LedgerRepository
    model_config: ModelConfigRepository
    max_session_jobs: int

    def orch(self, text_llm: TextLLMPort) -> ChatOrchestrator:
        return ChatOrchestrator(
            text_llm=text_llm, launcher=self.launcher, event_stream=self.events,
            registry=self.registry, chat_repo=self.chat_repo, pending=self.pending,
            query=self.query, ledger=self.ledger, model_config=self.model_config,
            max_session_jobs=self.max_session_jobs,
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
    query = SqlAlchemyListingHistoryQuery(sf)
    ledger = _FakeLedger()
    launcher = ListingJobLauncher(
        service=service, uploads=uploads, rate_limiter=UserRateLimiter(), events=events,
        history=SqlAlchemyListingHistory(sf), queue=InProcessTaskQueue(),
        query=query, image_store=LocalImageStore(tmp),
        media_signer=LocalMediaUrlSigner(""),
    )
    return Infra(
        launcher, uploads, registry, events, SqlAlchemyChatSessionRepository(sf),
        PendingStore(), query, ledger, _FakeModelConfig(), max_session_jobs,
    )


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
        assert cc["estimate_cny"] == str(unit * 5)  # 与工作台同源(#884③)
        assert ev[-1] == ("assistant_end", {"status": "awaiting_confirm"})
        sid = _first(ev, "session")["session_id"]
        # 费用闸：确认前 DB 无 job(未出图);user 消息已落、assistant 未落(答复留到 confirm)
        assert await inf.chat_repo.job_count(sid) == 0
        t = await inf.chat_repo.get_transcript(sid, USER.user_id)
        assert t is not None and [m.role for m in t.messages] == ["user"]

    asyncio.run(_impl())


def test_auto_ratio_uses_first_uploaded_image(tmp_path) -> None:
    async def _impl() -> None:
        inf = await _infra(str(tmp_path))
        first = await inf.uploads.save(
            data=_image_bytes(900, 1600), content_type="image/png", user_id=USER.user_id
        )
        second = await inf.uploads.save(
            data=_image_bytes(1600, 900), content_type="image/png", user_id=USER.user_id
        )
        llm = CapturingTextLLM()
        await _drain(inf.orch(llm).handle_message(USER, None, "给商品出图", [first, second]))
        assert "自动比例=9:16" in llm.messages[-1].content

    asyncio.run(_impl())


def test_auto_ratio_falls_back_when_first_upload_cannot_be_loaded(tmp_path) -> None:
    async def _impl() -> None:
        inf = await _infra(str(tmp_path))
        llm = CapturingTextLLM()
        await _drain(
            inf.orch(llm).handle_message(USER, None, "给商品出图", ["missing/image.png"])
        )
        assert "自动比例=1:1" in llm.messages[-1].content

    asyncio.run(_impl())


def test_auto_ratio_falls_back_when_upload_store_read_fails(tmp_path) -> None:
    async def _impl() -> None:
        inf = await _infra(str(tmp_path))
        inf.launcher.uploads.store = _ReadFailureUploadStore()
        upload_id = f"{upload_ns(USER.user_id)}/0000000000000000.png"
        llm = CapturingTextLLM()

        await _drain(
            inf.orch(llm).handle_message(USER, None, "给商品出图", [upload_id])
        )

        assert "自动比例=1:1" in llm.messages[-1].content

    asyncio.run(_impl())


def test_mock_text_llm_uses_first_upload_ratio_in_cost_confirm(tmp_path) -> None:
    async def _impl() -> None:
        inf = await _infra(str(tmp_path))
        uid = await inf.uploads.save(
            data=_image_bytes(900, 1600), content_type="image/png", user_id=USER.user_id
        )

        events = await _drain(
            inf.orch(MockTextLLMProvider()).handle_message(
                USER, None, "给商品出一张图", [uid]
            )
        )

        assert _first(events, "cost_confirm")["args"]["ratio"] == "9:16"

    asyncio.run(_impl())


def test_mock_text_llm_explicit_ratio_overrides_first_upload(tmp_path) -> None:
    async def _impl() -> None:
        inf = await _infra(str(tmp_path))
        uid = await inf.uploads.save(
            data=_image_bytes(900, 1600), content_type="image/png", user_id=USER.user_id
        )

        events = await _drain(
            inf.orch(MockTextLLMProvider()).handle_message(
                USER, None, "给商品出一张 3：4 的图", [uid]
            )
        )

        assert _first(events, "cost_confirm")["args"]["ratio"] == "3:4"

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
        # 转录：user 消息 + assistant 最终答复(带 job_id);过程态不落
        t = await inf.chat_repo.get_transcript(sid, USER.user_id)
        assert t is not None and [m.role for m in t.messages] == ["user", "assistant"]
        assert t.messages[1].job_id == _first(conf, "job_started")["job_id"]

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


def test_validation_clarification_hides_internal_field_names(tmp_path) -> None:
    """P3-#5：校验失败转澄清的用户文案=话术，不吐 upload_ids 等内部字段名。"""
    async def _impl() -> None:
        inf = await _infra(str(tmp_path))
        # LLM 产 upload_ids=[] 的 generate（漏带产品图）→ validate 失败 → 澄清而非报错
        bad = (
            ToolCall(
                id="c1", name="generate",
                arguments={"upload_ids": [], "prompt": "花生", "ratio": "1:1", "n": 1},
            ),
        )
        orch = inf.orch(StubTextLLM(("好的", bad)))
        ev = await _drain(orch.handle_message(USER, None, "出图", []))
        types = [t for t, _ in ev]
        assert "cost_confirm" not in types and "tool_call" not in types
        text = "".join(d.get("text", "") for t, d in ev if t == "assistant_delta")
        assert "请上传" in text  # 话术兜底
        for tok in ("upload_ids", "overlay_texts", "plan", "modifiers", "ratio", "category"):
            assert tok not in text
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


# ── 持久化(ISSUE-0051 验收)：刷新不丢 / owner 404 / CASCADE 删 ─────────────────


def test_transcript_persists_across_new_orchestrator(tmp_path) -> None:
    """验收①：会话与消息落库，新 orchestrator 实例(模拟刷新/重启)仍能回显。"""
    async def _impl() -> None:
        inf = await _infra(str(tmp_path))
        orch = inf.orch(StubTextLLM(("你好呀，需要出什么图？", ())))
        msg = await _drain(orch.handle_message(USER, None, "你好", []))
        sid = _first(msg, "session")["session_id"]
        # 新 orchestrator + 全新 PendingStore(内存态丢失)，共享同一 DB
        inf2 = Infra(
            inf.launcher, inf.uploads, inf.registry, inf.events, inf.chat_repo,
            PendingStore(), inf.query, inf.ledger, inf.model_config, inf.max_session_jobs,
        )
        t = await inf2.chat_repo.get_transcript(sid, USER.user_id)
        assert t is not None
        assert [m.role for m in t.messages] == ["user", "assistant"]
        assert t.messages[0].content == "你好"
        sessions = await inf2.chat_repo.list_sessions(USER.user_id)
        assert len(sessions) == 1 and sessions[0].id == sid and sessions[0].message_count == 2

    asyncio.run(_impl())


def test_get_transcript_owner_isolation_404(tmp_path) -> None:
    """验收③：越权他人会话 → None(路由 404 anti-enum)。"""
    async def _impl() -> None:
        inf = await _infra(str(tmp_path))
        orch = inf.orch(StubTextLLM(("在的~", ())))
        msg = await _drain(orch.handle_message(USER, None, "hi", []))
        sid = _first(msg, "session")["session_id"]
        assert await inf.chat_repo.get_transcript(sid, OTHER.user_id) is None
        assert await inf.chat_repo.list_sessions(OTHER.user_id) == []

    asyncio.run(_impl())


def test_delete_session_cascade_and_owner(tmp_path) -> None:
    """验收④：删会话级联删消息、列表消失；他人删→False(404)、不受影响。"""
    async def _impl() -> None:
        inf = await _infra(str(tmp_path))
        orch = inf.orch(StubTextLLM(("好的", ())))
        msg = await _drain(orch.handle_message(USER, None, "hi", []))
        sid = _first(msg, "session")["session_id"]
        assert await inf.chat_repo.delete_session(sid, OTHER.user_id) is False  # 他人删拒
        assert await inf.chat_repo.get_transcript(sid, USER.user_id) is not None  # 仍在
        assert await inf.chat_repo.delete_session(sid, USER.user_id) is True  # 本人删
        assert await inf.chat_repo.get_transcript(sid, USER.user_id) is None  # 级联消失
        assert await inf.chat_repo.list_sessions(USER.user_id) == []

    asyncio.run(_impl())


# ── ListingJobLauncher.validate 纯校验(#884⑤ 与出图同一校验源) ─────────────────


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


# ── PendingStore：confirm_token 一次性 / 过期 / clear ─────────────────────────


def _req() -> ListingGenerateRequest:
    return ListingGenerateRequest(upload_ids=["a"], prompt="p", ratio="1:1", n=1)


def test_pending_take_one_time_and_mismatch_preserves() -> None:
    p = PendingStore()
    action = p.new("s1", tool="generate", req=_req(), count=1, estimate=Decimal("0.4"))
    assert p.take("s1", "wrong") is None  # 不匹配不消费
    assert p.take("s1", action.confirm_token) is action  # 真 token 仍在
    assert p.take("s1", action.confirm_token) is None  # 一次性，二次拒


def test_pending_take_expired() -> None:
    p = PendingStore(ttl_seconds=-1.0)  # 立即过期
    action = p.new("s1", tool="generate", req=_req(), count=1, estimate=Decimal("0.4"))
    assert p.take("s1", action.confirm_token) is None  # 匹配但过期
    assert p.take("s1", action.confirm_token) is None  # 已消费


def test_pending_clear() -> None:
    p = PendingStore()
    action = p.new("s1", tool="generate", req=_req(), count=1, estimate=Decimal("0.4"))
    p.clear("s1")
    assert p.take("s1", action.confirm_token) is None


# ── A3 工具化：读工具（query_my_jobs/get_job_recipe/get_pricing_quota）验收⑥ ──


def test_read_tool_loop_executes_and_feeds_back(tmp_path) -> None:
    """读工具即时执行→结果回喂→LLM 收尾；不进费用闸（写工具才过闸）。"""
    async def _impl() -> None:
        inf = await _infra(str(tmp_path))
        tc = (ToolCall(id="q1", name="query_my_jobs", arguments={}),)
        orch = inf.orch(StubTextLLM(("", tc), ("你最近还没出过图哦。", ())))
        ev = await _drain(orch.handle_message(USER, None, "我最近出过什么图", []))
        types = [t for t, _ in ev]
        assert "cost_confirm" not in types and "tool_call" not in types  # 读工具不花钱不过闸
        assert any(t == "step" and d.get("phase") == "querying" for t, d in ev)
        text = "".join(d.get("text", "") for t, d in ev if t == "assistant_delta")
        assert "还没出过图" in text  # LLM 基于工具结果收尾
        assert ev[-1] == ("assistant_end", {"status": "complete"})

    asyncio.run(_impl())


def test_get_pricing_quota_reads_live_model_config(tmp_path) -> None:
    """波动值走实时查（#1043）：价格取 model_config 当前值、只列启用模型、额度取 ledger。"""
    async def _impl() -> None:
        inf = await _infra(str(tmp_path))
        out = await inf.orch(StubTextLLM(("", ())))._tool_get_pricing_quota(USER)
        assert "0.40" in out  # 实时价（非写死）
        assert "gpt-image-2" in out and "seedream-5" not in out  # 只列 enabled
        assert "剩余" in out  # 额度真数据

    asyncio.run(_impl())


def test_get_job_recipe_owner_isolation(tmp_path) -> None:
    """owner-scoped 护栏③：查不到他人/不存在的单，返同一话术不泄漏存在性。"""
    async def _impl() -> None:
        inf = await _infra(str(tmp_path))
        out = await inf.orch(StubTextLLM(("", ())))._tool_get_job_recipe(
            USER, {"job_id": "does-not-exist"}
        )
        assert "找不到" in out or "不属于" in out

    asyncio.run(_impl())


def test_query_my_jobs_returns_own_job_not_others(tmp_path) -> None:
    """真数据 + owner 隔离：出一单后本人可查、他人查为空。"""
    async def _impl() -> None:
        inf = await _infra(str(tmp_path))
        uid = await _stage(inf)
        orch = inf.orch(StubTextLLM(("好的", _gen_tc(uid, n=1))))
        msg = await _drain(orch.handle_message(USER, None, "出一张", [uid]))
        sid = _first(msg, "session")["session_id"]
        tok = _first(msg, "cost_confirm")["confirm_token"]
        await _drain(orch.handle_confirm(USER, sid, tok, "confirm"))
        mine = await inf.orch(StubTextLLM(("", ())))._tool_query_my_jobs(USER, {})
        assert "job_id=" in mine and "暂无出图记录" not in mine
        theirs = await inf.orch(StubTextLLM(("", ())))._tool_query_my_jobs(OTHER, {})
        assert "暂无出图记录" in theirs  # 他人查不到本人的单

    asyncio.run(_impl())
