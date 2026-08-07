"""「帮我设计」方案 C 对话编排 + 持久化单测（ISSUE-0048 chat 测试债 + ISSUE-0051 持久化）。

覆盖：ChatOrchestrator 事件序 / generation_confirm 暂停不出图 /
confirm 启 job+job_event 转发 /
confirm_token 一次性·跨用户·cancel·过期 / 会话级闸(DB 派生) / 占位 ratio→转澄清 / 澄清轮无工具;
ListingSubmissionService.validate 纯校验; PendingStore token 语义; ChatSessionRepository 持久化(刷新
不丢/owner 404/CASCADE 删/job_count) + 转录落库(user 消息+assistant 答复+job_id,过程态不落)。

出图提交与 Redis 事件流使用针对新端口的轻量 fake，持久化使用 sqlite。
文本 LLM 用确定性 Stub(真 provider 流式/工具解析在 test_text_llm_adapter.py 覆盖)。
"""

import asyncio
import logging
import uuid
from collections.abc import AsyncIterator
from dataclasses import dataclass, field, replace
from datetime import UTC, datetime
from decimal import Decimal
from io import BytesIO

import pytest
from PIL import Image
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from design_hub.application.chat.image_options import (
    AUTO_CHAT_IMAGE_OPTIONS,
    ChatImageOptions,
    ChatRenderTier,
)
from design_hub.application.chat.orchestrator import ChatOrchestrator
from design_hub.application.chat.pending_store import PendingStore
from design_hub.application.chat.ratio_intent import decide_chat_ratio
from design_hub.application.image_prompts.reverse_prompt import (
    ReversePromptService,
)
from design_hub.application.listing.background_replacement import (
    closest_supported_ratio,
)
from design_hub.application.listing.prompt_composer import (
    CategoryCardRegistry,
    CloneModeRegistry,
    EditModeRegistry,
    ImageTypeRegistry,
    PromptModifierRegistry,
)
from design_hub.application.listing.requests import (
    BackgroundReplaceRequest,
    CloneRequest,
    EditRequest,
    ListingGenerateRequest,
)
from design_hub.application.listing.submission_service import (
    ListingSubmissionService,
    SubmissionReceipt,
)
from design_hub.application.listing.task_planner import ListingTaskPlanner
from design_hub.application.listing.upload_service import UploadService
from design_hub.application.tasking.health import (
    QueueAdmissionController,
    QueueSnapshot,
    RedisHealthState,
)
from design_hub.domain.admin import ModelOperation
from design_hub.domain.enums import ModelType, ProviderType, Role, TaskEventType
from design_hub.domain.errors import NotFoundError
from design_hub.domain.models import (
    AuthUser,
    BudgetSnapshot,
    ListingJobImage,
    TaskEvent,
)
from design_hub.domain.tasking import RenderTier
from design_hub.infrastructure.db.base import Base
from design_hub.infrastructure.db.chat_repo import SqlAlchemyChatSessionRepository
from design_hub.infrastructure.db.listing_history_repo import SqlAlchemyListingHistory
from design_hub.infrastructure.db.listing_query_repo import SqlAlchemyListingHistoryQuery
from design_hub.infrastructure.providers.mock_text import MockTextLLMProvider
from design_hub.infrastructure.storage.local import LocalImageStore
from design_hub.infrastructure.storage.local_upload import LocalUploadStore
from design_hub.interface.chat_schemas import ChatMessageRequest
from design_hub.ports.chat_repository import ChatSessionRepository
from design_hub.ports.events import ReplayableEvent
from design_hub.ports.generation_work import JobSubmission, SubmitResult
from design_hub.ports.ledger import LedgerRepository
from design_hub.ports.model_calls import ModelCallContext
from design_hub.ports.model_config_repository import ModelConfigRecord, ModelConfigRepository
from design_hub.ports.text_llm import (
    ChatMessage,
    LLMChunk,
    TextChunk,
    TextLLMError,
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

    async def reserve(self, user_id: str, amount: Decimal, *, operation_id: str) -> None: ...

    async def rollback(self, user_id: str, amount: Decimal, *, operation_id: str) -> None: ...


class _FakeModelConfig(ModelConfigRepository):
    def __init__(
        self,
        *,
        standard_enabled: bool = True,
        four_k_enabled: bool = True,
        standard_cost: Decimal = Decimal("0.05"),
        four_k_cost: Decimal = Decimal("0.18"),
        include_four_k: bool = True,
    ) -> None:
        del four_k_enabled, four_k_cost, include_four_k
        self._c = [
            _model_record("gpt-image-2", standard_cost, standard_enabled),
            replace(
                _model_record("nano-banana-2", Decimal("0.12"), True),
                display_name="Nano Banana 2",
            ),
            _model_record("seedream-5", Decimal("0.20"), True),
        ]

    def set_enabled(self, name: str, enabled: bool) -> None:
        current = next(config for config in self._c if config.name == name)
        self._c[self._c.index(current)] = replace(current, enabled=enabled)

    async def list_all(self) -> list[ModelConfigRecord]:
        return list(self._c)

    async def get(self, name: str) -> ModelConfigRecord | None:
        return next((c for c in self._c if c.name == name), None)

    async def get_default(self, model_type: ModelType) -> str | None:
        del model_type
        return None

    async def update(self, *, actor_id, record):  # type: ignore[no-untyped-def]
        raise NotImplementedError

    async def create(self, *, actor_id, record):  # type: ignore[no-untyped-def]
        raise NotImplementedError

    async def delete(self, *, actor_id, name) -> None:  # type: ignore[no-untyped-def]
        raise NotImplementedError

    async def set_default(self, *, actor_id, name):  # type: ignore[no-untyped-def]
        raise NotImplementedError

    async def seed_defaults(self, defaults) -> None:  # type: ignore[no-untyped-def]
        raise NotImplementedError


def _model_record(name: str, unit_cost: Decimal, enabled: bool) -> ModelConfigRecord:
    return ModelConfigRecord(
        name=name,
        display_name=name,
        model_type=ModelType.IMAGE,
        provider_type=ProviderType.OPENAI_COMPAT_IMAGE,
        base_url="https://unused.example.test/v1",
        model=name,
        credentials_ciphertext={"standard_api_keys": ["test-ciphertext"]},
        unit_cost=unit_cost,
        enabled=enabled,
        revision=1,
        verified_at=datetime.now(UTC),
        verified_fingerprint="verified",
        extra={},
    )


class _NeverSubmitRepository:
    async def submit(self, submission: JobSubmission) -> SubmitResult:
        raise AssertionError("validation-only repository must not submit")


class _ZeroQueue:
    async def snapshot(self) -> QueueSnapshot:
        return QueueSnapshot(
            depth=0,
            rolling_item_seconds=60,
            available_slots=4,
        )


class _ReplayEvents:
    def __init__(self) -> None:
        self._events: dict[str, list[ReplayableEvent]] = {}

    def add(self, job_id: str, event_type: TaskEventType, data: dict) -> None:
        events = self._events.setdefault(job_id, [])
        events.append(
            ReplayableEvent(
                redis_id=f"{len(events) + 1}-0",
                event=TaskEvent(job_id=job_id, type=event_type, data=data),
            )
        )

    async def read(
        self, *, job_id: str, after_id: str, block_ms: int
    ) -> tuple[ReplayableEvent, ...]:
        del block_ms
        sequence = int(after_id.split("-", maxsplit=1)[0])
        return tuple(self._events.get(job_id, [])[sequence:])


class _FakeSubmission:
    def __init__(
        self,
        *,
        planner: ListingTaskPlanner,
        history: SqlAlchemyListingHistory,
        query: SqlAlchemyListingHistoryQuery,
        events: _ReplayEvents,
        uploads: UploadService,
        model_configs: _FakeModelConfig,
    ) -> None:
        health = RedisHealthState(stale_after_seconds=60)
        health.mark_healthy(now=0)
        self._validator = ListingSubmissionService(
            planner=planner,
            repository=_NeverSubmitRepository(),  # type: ignore[arg-type]
            query=query,
            uploads=uploads,
            redis_health=health,
            queue_snapshots=_ZeroQueue(),
            admission=QueueAdmissionController(
                soft_wait_seconds=300,
                confirm_wait_seconds=900,
                hard_depth=2000,
            ),
            model_configs=model_configs,
            clock=lambda: 0,
        )
        self._planner = planner
        self._history = history
        self._query = query
        self._events = events
        self._uploads = uploads
        self.calls: list[str] = []

    def validate(
        self,
        user_id: str,
        request: ListingGenerateRequest | CloneRequest | EditRequest,
        *,
        render_tier: RenderTier = RenderTier.STANDARD,
    ) -> None:
        self._validator.validate(user_id, request, render_tier=render_tier)

    async def submit_generate(
        self,
        *,
        user_id: str,
        request: ListingGenerateRequest,
        idempotency_key: str,
        trace_id: str,
        request_id: str,
        render_tier: RenderTier = RenderTier.STANDARD,
    ) -> SubmissionReceipt:
        submission = self._planner.plan_generate(
            user_id=user_id,
            request=request,
            job_id=uuid.uuid4().hex,
            idempotency_key=idempotency_key,
            trace_id=trace_id,
            request_id=request_id,
            model_id=request.image_model,
            unit_cost=Decimal("0.05"),
            render_tier=render_tier,
        )
        return await self._complete(submission, request.image_model)

    async def submit_clone(
        self,
        *,
        user_id: str,
        request: CloneRequest,
        idempotency_key: str,
        trace_id: str,
        request_id: str,
        render_tier: RenderTier = RenderTier.STANDARD,
    ) -> SubmissionReceipt:
        submission = self._planner.plan_clone(
            user_id=user_id,
            request=request,
            job_id=uuid.uuid4().hex,
            idempotency_key=idempotency_key,
            trace_id=trace_id,
            request_id=request_id,
            model_id=request.image_model,
            unit_cost=Decimal("0.05"),
            render_tier=render_tier,
        )
        return await self._complete(submission, request.image_model)

    async def submit_edit(
        self,
        *,
        user_id: str,
        request: EditRequest,
        idempotency_key: str,
        trace_id: str,
        request_id: str,
        render_tier: RenderTier = RenderTier.STANDARD,
    ) -> SubmissionReceipt:
        source = await self._query.resolve_generated_image_source(
            source_image_key=request.source_image_key,
            user_id=user_id,
        )
        if source is None:
            raise NotFoundError("源图不存在或无权访问，请重新选择后再试")
        submission = self._planner.plan_edit(
            user_id=user_id,
            request=request,
            source=source,
            job_id=uuid.uuid4().hex,
            idempotency_key=idempotency_key,
            trace_id=trace_id,
            request_id=request_id,
            model_id=request.image_model,
            unit_cost=Decimal("0.05"),
            render_tier=render_tier,
        )
        return await self._complete(submission, request.image_model)

    async def validate_background_replace(
        self,
        *,
        user_id: str,
        request: BackgroundReplaceRequest,
    ) -> None:
        await self._validator.validate_background_replace(
            user_id=user_id,
            request=request,
        )

    async def submit_background_replace(
        self,
        *,
        user_id: str,
        request: BackgroundReplaceRequest,
        idempotency_key: str,
        trace_id: str,
        request_id: str,
        render_tier: RenderTier = RenderTier.STANDARD,
    ) -> SubmissionReceipt:
        if request.source.kind == "upload":
            data, _content_type = await self._uploads.load(request.source.upload_id)
            source = None
            ratio = closest_supported_ratio(data)
        else:
            source = await self._query.resolve_generated_image_source(
                source_image_key=request.source.image_key,
                user_id=user_id,
            )
            if source is None:
                raise NotFoundError("源图不存在或无权访问，请重新选择后再试")
            ratio = source.parent_ratio
        submission = self._planner.plan_background_replace(
            user_id=user_id,
            request=request,
            source=source,
            ratio=ratio,
            job_id=uuid.uuid4().hex,
            idempotency_key=idempotency_key,
            trace_id=trace_id,
            request_id=request_id,
            model_id=request.image_model,
            unit_cost=Decimal("0.05"),
            render_tier=render_tier,
        )
        return await self._complete(submission, request.image_model)

    async def _complete(
        self,
        submission: JobSubmission,
        model: str,
    ) -> SubmissionReceipt:
        self.calls.append(model)
        await self._history.start(submission.job)
        images = tuple(
            ListingJobImage(
                image_key=f"{submission.job.job_id}-{item.sequence}.png",
                seed=item.seed,
                cost=item.reserved_cost,
                status="成功",
                image_type=item.image_type,
            )
            for item in submission.items
        )
        await self._history.add_images(submission.job.job_id, images)
        total_cost = sum(
            (image.cost for image in images),
            start=Decimal("0"),
        )
        await self._history.finalize(
            submission.job.job_id,
            status="完成",
            total_cost=total_cost,
            error=None,
        )
        self._events.add(
            submission.job.job_id,
            TaskEventType.TASK_STARTED,
            {},
        )
        for image in images:
            self._events.add(
                submission.job.job_id,
                TaskEventType.IMAGE_GENERATED,
                {
                    "image_key": image.image_key,
                    "image_type": image.image_type,
                },
            )
        self._events.add(
            submission.job.job_id,
            TaskEventType.TASK_COMPLETED,
            {"total_cost": str(total_cost)},
        )
        return SubmissionReceipt(
            job_id=submission.job.job_id,
            queue_state="normal",
            estimated_wait_seconds=0,
            replayed=False,
        )


class StubTextLLM(TextLLMPort):
    """确定性文本 LLM：每次带工具的调用取下一条脚本；收尾轮(无工具)产固定收尾语。"""

    is_live = False

    def __init__(self, *turns: tuple[str, tuple[ToolCall, ...]]) -> None:
        self._turns = list(turns)
        self._i = 0
        self.contexts: list[ModelCallContext] = []

    async def complete(
        self,
        *,
        context: ModelCallContext,
        messages: list[ChatMessage],
        tools: list[ToolSpec],
    ) -> AsyncIterator[LLMChunk]:
        self.contexts.append(context)
        if not tools:  # 收尾轮
            yield TextChunk("已完成，可在结果区查看。")
            return
        text, calls = self._turns[min(self._i, len(self._turns) - 1)]
        self._i += 1
        if text:
            yield TextChunk(text)
        if calls:
            yield ToolCallChunk(calls)


_REVERSE_RESULT = {
    "summary": "暖色咖啡店中的商品摄影",
    "subject": "银白色无线耳机充电盒",
    "scene": "现代咖啡店木质桌面",
    "composition": "商品居中偏下，背景虚化",
    "camera": "接近平视的中近景产品摄影",
    "lighting": "左前方柔和自然光",
    "colors": ["暖棕色", "银白色"],
    "style": "写实商业产品摄影",
    "visible_text": [],
    "constraints": ["保持商品比例和金属材质"],
    "uncertainties": ["无法仅根据图片确定真实焦段"],
    "prompt_zh": "银白色无线耳机充电盒置于咖啡店木桌上",
    "prompt_en": "A silver wireless earbud charging case on a cafe table",
}


class _ReverseTextLLM(TextLLMPort):
    is_live = True

    async def complete(
        self,
        *,
        context: ModelCallContext,
        messages: list[ChatMessage],
        tools: list[ToolSpec],
    ) -> AsyncIterator[LLMChunk]:
        del context
        yield ToolCallChunk(
            (
                ToolCall(
                    id="reverse-result",
                    name="return_reverse_prompt",
                    arguments=_REVERSE_RESULT,
                ),
            )
        )


class ChunkedTextLLM(TextLLMPort):
    is_live = False

    def __init__(self, chunks: tuple[str, ...]) -> None:
        self._chunks = chunks

    async def complete(
        self,
        *,
        context: ModelCallContext,
        messages: list[ChatMessage],
        tools: list[ToolSpec],
    ) -> AsyncIterator[LLMChunk]:
        del context
        for chunk in self._chunks:
            yield TextChunk(chunk)


class CapturingTextLLM(TextLLMPort):
    is_live = False

    def __init__(self) -> None:
        self.messages: list[ChatMessage] = []

    async def complete(
        self,
        *,
        context: ModelCallContext,
        messages: list[ChatMessage],
        tools: list[ToolSpec],
    ) -> AsyncIterator[LLMChunk]:
        del context
        self.messages = messages
        yield TextChunk("请确认设计要求。")


class LateFailingTextLLM(TextLLMPort):
    is_live = False

    async def complete(
        self,
        *,
        context: ModelCallContext,
        messages: list[ChatMessage],
        tools: list[ToolSpec],
    ) -> AsyncIterator[LLMChunk]:
        del context
        yield TextChunk("已收到，")
        yield TextChunk("正在处理")
        raise TextLLMError("文本服务暂时不可用")


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


def test_prepare_generate_args_forces_deterministic_landscape_ratio() -> None:
    args = ChatOrchestrator._prepare_write_args(
        "generate",
        {"upload_ids": ["u"], "prompt": "主图", "ratio": "1:1", "n": 1},
        decide_chat_ratio("做横版主图", "3:4"),
        None,
        None,
    )

    assert args["ratio"] == "4:3"


def test_prepare_edit_args_uses_selected_key_and_inherits_ratio_for_delta() -> None:
    args = ChatOrchestrator._prepare_write_args(
        "edit",
        {
            "source_image_key": "hallucinated.png",
            "prompt": "背景换成海边",
            "edit_mode": "delta",
            "ratio": "1:1",
        },
        decide_chat_ratio("背景换成海边", "1:1"),
        "selected.png",
        None,
    )

    assert args == {
        "source_image_key": "selected.png",
        "prompt": "背景换成海边",
        "edit_mode": "delta",
    }


def test_prepare_edit_args_promotes_ratio_change_to_full() -> None:
    args = ChatOrchestrator._prepare_write_args(
        "edit",
        {
            "source_image_key": "wrong.png",
            "prompt": "改成横版",
            "edit_mode": "delta",
        },
        decide_chat_ratio("改成横版", "1:1"),
        "selected.png",
        None,
    )

    assert args["source_image_key"] == "selected.png"
    assert args["edit_mode"] == "full"
    assert args["ratio"] == "4:3"


def test_prepare_edit_args_rejects_missing_ui_selection() -> None:
    with pytest.raises(ValueError, match="先在结果图上点击"):
        ChatOrchestrator._prepare_write_args(
            "edit",
            {"source_image_key": "guessed.png", "prompt": "改暖色", "edit_mode": "delta"},
            decide_chat_ratio("改暖色", "1:1"),
            None,
            None,
        )


@pytest.mark.parametrize(
    ("tool", "args"),
    [
        (
            "clone",
            {
                "product_upload_ids": ["product"],
                "reference_upload_ids": ["reference"],
                "clone_mode": "参考风格",
                "ratio": "1:1",
            },
        ),
        (
            "edit",
            {
                "source_image_key": "selected.png",
                "prompt": "调整光线",
                "edit_mode": "delta",
            },
        ),
        (
            "replace_background",
            {
                "source": {"kind": "upload", "upload_id": "product"},
                "background": {"kind": "description", "description": "暖色背景"},
            },
        ),
    ],
)
def test_non_generate_tools_reject_multi_image_selection(
    tool: str,
    args: dict,
) -> None:
    with pytest.raises(ValueError, match="一次只生成 1 张"):
        ChatOrchestrator._prepare_write_args(
            tool,
            args,
            decide_chat_ratio("保持原图", "1:1"),
            "selected.png",
            2,
        )


def test_background_replace_rejects_explicit_ratio_selection() -> None:
    with pytest.raises(ValueError, match="保持源图比例"):
        ChatOrchestrator._prepare_write_args(
            "replace_background",
            {
                "source": {"kind": "upload", "upload_id": "product"},
                "background": {"kind": "description", "description": "暖色背景"},
            },
            decide_chat_ratio("改成 4:5", "1:1"),
            None,
            1,
        )


def test_chat_generate_converts_to_category_free_listing_request() -> None:
    req = ChatOrchestrator._parse_req(
        "generate",
        {
            "upload_ids": ["u"],
            "prompt": "主体居中，柔和棚拍光，保留原图 Logo",
            "ratio": "1:1",
            "n": 1,
        },
        "gpt-image-2",
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
            "gpt-image-2",
        )


def test_logo_request_uses_enhanced_prompt_without_category_clarification(tmp_path) -> None:
    async def _impl() -> None:
        inf = await _infra(str(tmp_path))
        uid = await _stage(inf)
        enhanced = (
            "以用户上传图为主体，设计简洁现代的 Logo 视觉；保持原图已有文字与标识不变，"
            "主体居中，留白充足，使用清晰矢量感边缘，不新增品牌名或宣传文案。"
        )
        orch = inf.orch(StubTextLLM(("正在完善设计要求", _gen_tc(uid, n=1, prompt=enhanced))))

        events = await _drain(orch.handle_message(USER, None, "帮我做一个简洁现代的 Logo", [uid]))

        confirm = _first(events, "generation_confirm")
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
    submission: _FakeSubmission
    uploads: UploadService
    events: _ReplayEvents
    chat_repo: ChatSessionRepository
    pending: PendingStore
    query: SqlAlchemyListingHistoryQuery
    model_config: _FakeModelConfig
    max_session_jobs: int
    reverse_prompt: ReversePromptService

    def orch(self, text_llm: TextLLMPort) -> ChatOrchestrator:
        return _TestChatOrchestrator(
            text_llm_resolver=_TextResolver(text_llm),
            submission=self.submission,  # type: ignore[arg-type]
            event_stream=self.events,
            uploads=self.uploads,
            chat_repo=self.chat_repo,
            pending=self.pending,
            query=self.query,
            model_config=self.model_config,
            max_session_jobs=self.max_session_jobs,
            reverse_prompt=self.reverse_prompt,
        )


@dataclass(frozen=True)
class _TextResolver:
    text_llm: TextLLMPort
    requested_model_ids: list[str] = field(default_factory=list)
    requested_model_types: list[ModelType] = field(default_factory=list)

    async def resolve(
        self,
        model_id: str,
        model_type: ModelType,
    ) -> TextLLMPort:
        self.requested_model_ids.append(model_id)
        self.requested_model_types.append(model_type)
        return self.text_llm

    async def resolve_default(self, model_type: ModelType) -> TextLLMPort:
        self.requested_model_types.append(model_type)
        return self.text_llm


class _TestChatOrchestrator(ChatOrchestrator):
    async def handle_message(
        self,
        user: AuthUser,
        session_id: str | None,
        message: str,
        upload_ids: list[str],
        *,
        chat_model: str = "doubao-chat",
        image_model: str = "gpt-image-2",
        image_options: ChatImageOptions = AUTO_CHAT_IMAGE_OPTIONS,
        edit_source_image_key: str | None = None,
    ) -> AsyncIterator:
        async for event in super().handle_message(
            user,
            session_id,
            message,
            upload_ids,
            chat_model=chat_model,
            image_model=image_model,
            image_options=image_options,
            edit_source_image_key=edit_source_image_key,
        ):
            yield event


async def _infra(
    tmp: str,
    *,
    max_session_jobs: int = 5,
    standard_enabled: bool = True,
    four_k_enabled: bool = True,
    standard_cost: Decimal = Decimal("0.05"),
    four_k_cost: Decimal = Decimal("0.18"),
    include_four_k: bool = True,
) -> Infra:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    sf = async_sessionmaker(engine, expire_on_commit=False)
    planner = ListingTaskPlanner(
        modifier_registry=PromptModifierRegistry(),
        card_registry=CategoryCardRegistry(),
        type_registry=ImageTypeRegistry(),
        clone_registry=CloneModeRegistry(),
        edit_registry=EditModeRegistry(),
    )
    events = _ReplayEvents()
    uploads = UploadService(store=LocalUploadStore(tmp))
    query = SqlAlchemyListingHistoryQuery(sf)
    model_config = _FakeModelConfig(
        standard_enabled=standard_enabled,
        four_k_enabled=four_k_enabled,
        standard_cost=standard_cost,
        four_k_cost=four_k_cost,
        include_four_k=include_four_k,
    )
    submission = _FakeSubmission(
        planner=planner,
        history=SqlAlchemyListingHistory(sf),
        query=query,
        events=events,
        uploads=uploads,
        model_configs=model_config,
    )
    reverse_prompt = ReversePromptService(
        text_llm_resolver=_TextResolver(_ReverseTextLLM()),
        uploads=uploads,
        images=LocalImageStore(tmp),
        query=query,
    )
    return Infra(
        submission,
        uploads,
        events,
        SqlAlchemyChatSessionRepository(sf),
        PendingStore(),
        query,
        model_config,
        max_session_jobs,
        reverse_prompt,
    )


async def _drain(agen: AsyncIterator) -> list[tuple[str, dict]]:
    return [(e.type, e.data) async for e in agen]


async def _stage(inf: Infra, user: AuthUser = USER) -> str:
    return await inf.uploads.save(data=_PNG, content_type="image/png", user_id=user.user_id)


def _first(events: list[tuple[str, dict]], type_: str) -> dict:
    return next(d for t, d in events if t == type_)


# ── ChatOrchestrator 事件序 + 费用闸 ──────────────────────────────────────────


def test_chat_message_request_requires_selected_text_model() -> None:
    with pytest.raises(ValueError):
        ChatMessageRequest(
            message="帮我设计",
            image_model="gpt-image-2",
        )


def test_selected_text_model_is_retained_for_confirmation(tmp_path) -> None:
    async def _impl() -> None:
        inf = await _infra(str(tmp_path))
        uid = await _stage(inf)
        orch = inf.orch(StubTextLLM(("", _gen_tc(uid, n=1))))
        resolver = orch.text_llm_resolver

        planned = await _drain(
            orch.handle_message(
                USER,
                None,
                "出一张",
                [uid],
                chat_model="deepseek-v4-flash",
                image_model="gpt-image-2",
            )
        )
        session_id = _first(planned, "session")["session_id"]
        pending = inf.pending._pending[session_id]
        assert pending.chat_model == "deepseek-v4-flash"
        assert resolver.requested_model_ids == ["deepseek-v4-flash"]
        assert resolver.requested_model_types == [ModelType.CHAT]

        await _drain(
            orch.handle_confirm(
                USER,
                session_id,
                pending.confirm_token,
                "confirm",
            )
        )
        assert resolver.requested_model_ids == [
            "deepseek-v4-flash",
            "deepseek-v4-flash",
        ]
        assert resolver.requested_model_types == [
            ModelType.CHAT,
            ModelType.CHAT,
        ]

    asyncio.run(_impl())


def test_valid_tool_call_reaches_generation_confirm_without_generating(tmp_path) -> None:
    async def _impl() -> None:
        inf = await _infra(str(tmp_path))
        uid = await _stage(inf)
        orch = inf.orch(StubTextLLM(("好的，我来帮你出一套图。", _gen_tc(uid, plan=_PLAN))))
        ev = await _drain(orch.handle_message(USER, None, "给我的花生出一套5张", [uid]))
        types = [t for t, _ in ev]
        assert types == [
            "session",
            "step",
            "tool_call",
            "generation_confirm",
            "assistant_end",
        ]
        assert _first(ev, "tool_call")["tool"] == "generate"
        cc = _first(ev, "generation_confirm")
        assert cc["count"] == 5
        sid = _first(ev, "session")["session_id"]
        assert inf.pending._pending[sid].image_model == "gpt-image-2"
        assert ev[-1] == ("assistant_end", {"status": "awaiting_confirm"})
        # 费用闸：确认前 DB 无 job(未出图);user 消息已落、assistant 未落(答复留到 confirm)
        assert await inf.chat_repo.job_count(sid) == 0
        t = await inf.chat_repo.get_transcript(sid, USER.user_id)
        assert t is not None and [m.role for m in t.messages] == ["user"]

    asyncio.run(_impl())


def test_background_replace_goes_directly_to_generation_confirmation(tmp_path) -> None:
    async def _impl() -> None:
        inf = await _infra(str(tmp_path))
        upload_id = await inf.uploads.save(
            data=_image_bytes(900, 1200),
            content_type="image/png",
            user_id=USER.user_id,
        )
        call = (
            ToolCall(
                id="background-1",
                name="replace_background",
                arguments={
                    "source": {
                        "kind": "upload",
                        "upload_id": upload_id,
                    },
                    "background": {
                        "kind": "description",
                        "description": "明亮的现代咖啡店",
                    },
                },
            ),
        )
        orchestrator = inf.orch(StubTextLLM(("", call)))

        planned = await _drain(
            orchestrator.handle_message(
                USER,
                None,
                "把这张商品图换成明亮咖啡店背景",
                [upload_id],
            )
        )

        assert _first(planned, "tool_call")["tool"] == "replace_background"
        confirmation = _first(planned, "generation_confirm")
        assert confirmation["count"] == 1
        assert confirmation["args"]["background"]["description"] == ("明亮的现代咖啡店")
        session_id = _first(planned, "session")["session_id"]
        confirmed = await _drain(
            orchestrator.handle_confirm(
                USER,
                session_id,
                confirmation["confirm_token"],
                "confirm",
            )
        )
        assert _first(confirmed, "job_started")["tool"] == "replace_background"

    asyncio.run(_impl())


def test_reverse_prompt_returns_server_rendered_text_without_cost_gate(
    tmp_path,
) -> None:
    async def _impl() -> None:
        inf = await _infra(str(tmp_path))
        upload_id = await inf.uploads.save(
            data=_image_bytes(1024, 1024),
            content_type="image/png",
            user_id=USER.user_id,
        )
        call = (
            ToolCall(
                id="reverse-1",
                name="reverse_prompt",
                arguments={
                    "source": {
                        "kind": "upload",
                        "upload_id": upload_id,
                    }
                },
            ),
        )

        events = await _drain(
            inf.orch(StubTextLLM(("", call))).handle_message(
                USER,
                None,
                "反推这张图的提示词",
                [upload_id],
            )
        )

        types = [event_type for event_type, _data in events]
        assert "generation_confirm" not in types
        assert "tool_call" not in types
        text = "".join(
            data.get("text", "") for event_type, data in events if event_type == "assistant_delta"
        )
        assert "中文提示词" in text
        assert _REVERSE_RESULT["prompt_zh"] in text
        assert events[-1] == ("assistant_end", {"status": "complete"})

    asyncio.run(_impl())


def test_open_feature_emits_prefilled_action_card_without_submitting(
    tmp_path,
) -> None:
    async def _impl() -> None:
        inf = await _infra(str(tmp_path))
        upload_id = await inf.uploads.save(
            data=_image_bytes(1024, 1024),
            content_type="image/png",
            user_id=USER.user_id,
        )
        call = (
            ToolCall(
                id="open-1",
                name="open_feature",
                arguments={
                    "feature": "background_replace",
                    "source": {
                        "kind": "upload",
                        "upload_id": upload_id,
                    },
                    "background": {
                        "kind": "description",
                        "description": "极简摄影棚",
                    },
                },
            ),
        )

        events = await _drain(
            inf.orch(StubTextLLM(("", call))).handle_message(
                USER,
                None,
                "打开换背景页面，我想仔细调整",
                [upload_id],
            )
        )

        card = _first(events, "action_card")
        assert card["feature"] == "background_replace"
        assert card["prefill"] == {
            "source_kind": "upload",
            "source_id": upload_id,
            "background_kind": "description",
            "background_description": "极简摄影棚",
        }
        assert "generation_confirm" not in [event_type for event_type, _ in events]
        assert inf.submission.calls == []

    asyncio.run(_impl())


def test_4k_tool_call_uses_real_price_ratio_and_pending_model(tmp_path) -> None:
    async def _impl() -> None:
        inf = await _infra(str(tmp_path))
        uid = await _stage(inf)
        events = await _drain(
            inf.orch(StubTextLLM(("", _gen_tc(uid, ratio="1:1", n=1)))).handle_message(
                USER, None, "生成一张 4K 主图", [uid]
            )
        )

        session_id = _first(events, "session")["session_id"]
        confirm = _first(events, "generation_confirm")
        assert confirm["args"]["ratio"] == "16:9"
        assert inf.pending._pending[session_id].image_model == "gpt-image-2"

    asyncio.run(_impl())


def test_national_style_4k_request_reaches_4k_generation_confirm_without_modifiers(
    tmp_path,
) -> None:
    async def _impl() -> None:
        inf = await _infra(str(tmp_path))
        uid = await _stage(inf)
        prompt = "以用户上传图为主体，设计国风风格画面，保持产品事实与已有文字不变"
        events = await _drain(
            inf.orch(
                StubTextLLM(("", _gen_tc(uid, ratio="1:1", n=1, prompt=prompt)))
            ).handle_message(USER, None, "我要生成 4K 图，国风风格的", [uid])
        )

        confirm = _first(events, "generation_confirm")
        assert confirm["args"]["ratio"] == "16:9"
        assert confirm["args"]["prompt"] == prompt
        assert "modifiers" not in confirm["args"]

    asyncio.run(_impl())


def test_4k_conflicting_ratio_stops_before_cost_pending_or_job(tmp_path) -> None:
    async def _impl() -> None:
        inf = await _infra(str(tmp_path))
        uid = await _stage(inf)
        events = await _drain(
            inf.orch(
                StubTextLLM(("好的，我来帮你出图。", _gen_tc(uid, ratio="4:3", n=1)))
            ).handle_message(USER, None, "生成 4K，比例 4:3", [uid])
        )

        session_id = _first(events, "session")["session_id"]
        event_types = [event_type for event_type, _data in events]
        text = "".join(
            data["text"]
            for event_type, data in events
            if event_type == "assistant_delta"
        )
        assert "gpt-image-2 4k 不支持 4:3" in text
        assert "16:9" in text
        assert "tool_call" not in event_types
        assert "generation_confirm" not in event_types
        assert session_id not in inf.pending._pending
        assert await inf.chat_repo.job_count(session_id) == 0

    asyncio.run(_impl())


def test_4k_with_standard_only_ratio_uses_4k_constraint_message(tmp_path) -> None:
    async def _impl() -> None:
        inf = await _infra(str(tmp_path))
        uid = await _stage(inf)
        events = await _drain(
            inf.orch(StubTextLLM(("", _gen_tc(uid, ratio="2:3", n=1)))).handle_message(
                USER, None, "生成 4K，比例 2:3", [uid]
            )
        )

        text = "".join(
            data["text"] for event_type, data in events if event_type == "assistant_delta"
        )
        assert "gpt-image-2 4k 不支持 2:3" in text
        assert "16:9" in text
        assert "tool_call" not in [event_type for event_type, _data in events]
        assert "generation_confirm" not in [event_type for event_type, _data in events]

    asyncio.run(_impl())


def test_explicit_4k_note_reaches_llm_before_write_tool_selection(tmp_path) -> None:
    async def _impl() -> None:
        inf = await _infra(str(tmp_path))
        llm = CapturingTextLLM()
        events = await _drain(inf.orch(llm).handle_message(USER, None, "4K 可以做成 4:3 吗？", []))

        assert "当前图片模型=gpt-image-2" in llm.messages[-1].content
        assert "当前清晰度=4k" in llm.messages[-1].content
        assert "当前模型与清晰度支持的比例=16:9" in llm.messages[-1].content
        assert "用户明确要求比例=4:3" in llm.messages[-1].content
        assert "4K 当前仅支持" not in "".join(
            data.get("text", "") for event_type, data in events if event_type == "assistant_delta"
        )
        assert events[-1] == ("assistant_end", {"status": "complete"})

    asyncio.run(_impl())


def test_selected_nano_banana_capabilities_reach_llm_before_reply(tmp_path) -> None:
    async def _impl() -> None:
        inf = await _infra(str(tmp_path))
        llm = CapturingTextLLM()

        await _drain(
            inf.orch(llm).handle_message(
                USER,
                None,
                "我现在需要做一张 1:8 的商品详情页图片",
                [],
                image_model="nano-banana-2",
                image_options=ChatImageOptions(
                    render_tier=ChatRenderTier.FOUR_K,
                    ratio="1:8",
                    count=1,
                ),
            )
        )

        note = llm.messages[-1].content
        assert "当前图片模型=Nano Banana 2" in note
        assert "当前清晰度=4k" in note
        assert "当前模型与清晰度支持的比例=" in note
        assert "1:8" in note
        assert "必须依据本备注回答模型能力问题" in note

    asyncio.run(_impl())


def test_chat_without_tool_replays_every_buffered_text_chunk(
    tmp_path,
    caplog,
) -> None:
    caplog.set_level(logging.INFO)

    async def _impl() -> None:
        inf = await _infra(str(tmp_path))
        events = await _drain(
            inf.orch(ChunkedTextLLM(("4K 当前", "支持 16:9 横版。"))).handle_message(
                USER, None, "4K 支持什么比例？", []
            )
        )

        deltas = [data["text"] for event_type, data in events if event_type == "assistant_delta"]
        assert deltas == ["4K 当前", "支持 16:9 横版。"]
        assert "".join(deltas) == "4K 当前支持 16:9 横版。"
        assert events[-1] == ("assistant_end", {"status": "complete"})

    asyncio.run(_impl())
    records = {
        record.msg: record
        for record in caplog.records
        if str(record.msg).startswith("chat_model_")
    }
    assert records["chat_model_started"].levelno == logging.INFO
    assert records["chat_model_started"].chain == "chat"
    assert records["chat_model_started"].action == "开始调用对话模型"
    assert records["chat_model_completed"].levelno == logging.INFO
    assert records["chat_model_completed"].action == "对话模型调用完成"


def test_late_llm_error_replays_and_persists_partial_assistant_text(
    tmp_path,
    caplog,
) -> None:
    caplog.set_level(logging.INFO)

    async def _impl() -> None:
        inf = await _infra(str(tmp_path))
        events = await _drain(
            inf.orch(LateFailingTextLLM()).handle_message(USER, None, "帮我设计", [])
        )

        assert [data["text"] for event_type, data in events if event_type == "assistant_delta"] == [
            "已收到，",
            "正在处理",
        ]
        assert [event_type for event_type, _data in events][-2:] == [
            "error",
            "assistant_end",
        ]
        session_id = _first(events, "session")["session_id"]
        transcript = await inf.chat_repo.get_transcript(session_id, USER.user_id)
        assert transcript is not None
        assert [message.role for message in transcript.messages] == ["user", "assistant"]
        assert transcript.messages[-1].content == "已收到，正在处理"

    asyncio.run(_impl())
    record = next(
        item
        for item in caplog.records
        if item.msg == "chat_model_failed"
    )
    assert record.levelno == logging.ERROR
    assert record.chain == "chat"
    assert record.action == "对话模型调用失败"


def test_non_gpt_model_cannot_be_used_for_4k(tmp_path) -> None:
    async def _impl() -> None:
        inf = await _infra(str(tmp_path))
        uid = await _stage(inf)
        events = await _drain(
            inf.orch(StubTextLLM(("", _gen_tc(uid, n=1)))).handle_message(
                USER,
                None,
                "生成 4K 主图",
                [uid],
                image_model="seedream-5",
            )
        )

        session_id = _first(events, "session")["session_id"]
        event_types = [event_type for event_type, _data in events]
        error = _first(events, "error")
        assert error == {
            "code": "model_unavailable",
            "message": "当前图片模型已不可用，请重新选择。",
        }
        assert "generation_confirm" not in event_types
        assert session_id not in inf.pending._pending
        assert await inf.chat_repo.job_count(session_id) == 0

    asyncio.run(_impl())


def test_4k_batch_count_reaches_confirmation_before_any_job_is_created(tmp_path) -> None:
    async def _impl() -> None:
        inf = await _infra(str(tmp_path))
        uid = await _stage(inf)
        events = await _drain(
            inf.orch(StubTextLLM(("", _gen_tc(uid, n=4)))).handle_message(
                USER, None, "生成 4 张 4K 主图", [uid]
            )
        )

        session_id = _first(events, "session")["session_id"]
        event_types = [event_type for event_type, _data in events]
        confirmation = _first(events, "generation_confirm")
        assert "tool_call" in event_types
        assert confirmation["count"] == 4
        assert confirmation["render_tier"] == "4k"
        assert confirmation["ratio"] == "16:9"
        assert session_id in inf.pending._pending
        assert await inf.chat_repo.job_count(session_id) == 0

    asyncio.run(_impl())


def test_4k_capability_question_without_write_tool_does_not_create_pending(tmp_path) -> None:
    async def _impl() -> None:
        inf = await _infra(str(tmp_path))
        events = await _drain(
            inf.orch(StubTextLLM(("4K 当前支持 16:9 横版。", ()))).handle_message(
                USER, None, "4K 支持什么比例？", []
            )
        )

        session_id = _first(events, "session")["session_id"]
        assert "generation_confirm" not in [event_type for event_type, _data in events]
        assert session_id not in inf.pending._pending
        assert await inf.chat_repo.job_count(session_id) == 0

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
        assert "本轮确定比例=9:16" in llm.messages[-1].content

    asyncio.run(_impl())


def test_auto_ratio_falls_back_when_first_upload_cannot_be_loaded(tmp_path) -> None:
    async def _impl() -> None:
        inf = await _infra(str(tmp_path))
        llm = CapturingTextLLM()
        await _drain(inf.orch(llm).handle_message(USER, None, "给商品出图", ["missing/image.png"]))
        assert "本轮确定比例=1:1" in llm.messages[-1].content

    asyncio.run(_impl())


def test_auto_ratio_falls_back_when_upload_store_read_fails(tmp_path) -> None:
    async def _impl() -> None:
        inf = await _infra(str(tmp_path))
        inf.uploads.store = _ReadFailureUploadStore()
        upload_id = f"{upload_ns(USER.user_id)}/0000000000000000.png"
        llm = CapturingTextLLM()

        await _drain(inf.orch(llm).handle_message(USER, None, "给商品出图", [upload_id]))

        assert "本轮确定比例=1:1" in llm.messages[-1].content

    asyncio.run(_impl())


def test_selected_edit_source_is_injected_only_into_llm_context(tmp_path) -> None:
    async def _impl() -> None:
        inf = await _infra(str(tmp_path))
        llm = CapturingTextLLM()
        events = await _drain(
            inf.orch(llm).handle_message(
                USER,
                None,
                "把背景改成海边",
                [],
                edit_source_image_key="selected.png",
            )
        )

        assert "source_image_key=selected.png" in llm.messages[-1].content
        session_id = _first(events, "session")["session_id"]
        transcript = await inf.chat_repo.get_transcript(session_id, USER.user_id)
        assert transcript is not None
        assert transcript.messages[0].content == "把背景改成海边"
        assert transcript.messages[0].attachment_upload_ids == ()

    asyncio.run(_impl())


def test_invalid_selected_source_never_creates_or_charges_a_job(tmp_path) -> None:
    async def _impl() -> None:
        inf = await _infra(str(tmp_path))
        call = ToolCall(
            id="edit-1",
            name="edit",
            arguments={
                "source_image_key": "model-guessed.png",
                "prompt": "改暖色",
                "edit_mode": "delta",
            },
        )
        planned = await _drain(
            inf.orch(StubTextLLM(("好的，我来调整。", (call,)))).handle_message(
                USER,
                None,
                "改暖色",
                [],
                edit_source_image_key="missing.png",
            )
        )
        session_id = _first(planned, "session")["session_id"]
        confirm_token = _first(planned, "generation_confirm")["confirm_token"]
        confirmed = await _drain(
            inf.orch(StubTextLLM(("完成", ()))).handle_confirm(
                USER, session_id, confirm_token, "confirm"
            )
        )

        assert _first(confirmed, "error")["code"] == "bad_request"
        assert await inf.chat_repo.job_count(session_id) == 0

    asyncio.run(_impl())


def test_mock_text_llm_uses_selected_image_for_edit(tmp_path) -> None:
    async def _impl() -> None:
        inf = await _infra(str(tmp_path))
        events = await _drain(
            inf.orch(MockTextLLMProvider()).handle_message(
                USER,
                None,
                "把背景换成海边",
                [],
                edit_source_image_key="selected.png",
            )
        )

        assert "tool_call" in [event_type for event_type, _data in events]
        tool_call = _first(events, "tool_call")
        assert tool_call["tool"] == "edit"
        assert tool_call["args"]["source_image_key"] == "selected.png"
        assert tool_call["args"]["edit_mode"] == "delta"
        assert _first(events, "generation_confirm")["count"] == 1

    asyncio.run(_impl())


def test_mock_text_llm_uses_first_upload_ratio_in_generation_confirm(tmp_path) -> None:
    async def _impl() -> None:
        inf = await _infra(str(tmp_path))
        uid = await inf.uploads.save(
            data=_image_bytes(900, 1600), content_type="image/png", user_id=USER.user_id
        )

        events = await _drain(
            inf.orch(MockTextLLMProvider()).handle_message(USER, None, "给商品出一张图", [uid])
        )

        assert _first(events, "generation_confirm")["args"]["ratio"] == "9:16"

    asyncio.run(_impl())


def test_mock_text_llm_explicit_ratio_overrides_first_upload(tmp_path) -> None:
    async def _impl() -> None:
        inf = await _infra(str(tmp_path))
        uid = await inf.uploads.save(
            data=_image_bytes(900, 1600), content_type="image/png", user_id=USER.user_id
        )

        events = await _drain(
            inf.orch(MockTextLLMProvider()).handle_message(
                USER, None, "给商品出一张 3：2 的图", [uid]
            )
        )

        assert _first(events, "generation_confirm")["args"]["ratio"] == "3:2"

    asyncio.run(_impl())


def test_confirm_launches_job_and_forwards_job_events(tmp_path) -> None:
    async def _impl() -> None:
        inf = await _infra(str(tmp_path))
        uid = await _stage(inf)
        orch = inf.orch(StubTextLLM(("", _gen_tc(uid, plan=_PLAN))))
        msg = await _drain(orch.handle_message(USER, None, "出一套", [uid]))
        sid = _first(msg, "session")["session_id"]
        tok = _first(msg, "generation_confirm")["confirm_token"]
        stream = orch.handle_confirm(USER, sid, tok, "confirm")
        prefix: list[tuple[str, dict]] = []
        async for event in stream:
            prefix.append((event.type, event.data))
            if event.type == "job_started":
                break

        job_id = _first(prefix, "job_started")["job_id"]
        running = await inf.chat_repo.get_transcript(sid, USER.user_id)
        assert running is not None
        assert [message.job_id for message in running.messages] == [None, job_id]
        assert running.messages[1].content == "生图任务详情如下："

        suffix = [(event.type, event.data) async for event in stream]
        conf = [*prefix, *suffix]
        types = [t for t, _ in conf]
        assert "job_started" in types
        assert _first(conf, "job_started")["plan"] == _PLAN
        job_events = [d for t, d in conf if t == "job_event"]
        assert all(
            isinstance(event["redis_id"], str) and event["redis_id"]
            for event in job_events
        )
        je = [d["type"] for d in job_events]
        assert "task_started" in je
        assert je.count("image_generated") == 5
        assert "task_completed" in je
        assert conf[-1] == ("assistant_end", {"status": "complete"})
        completed = await inf.chat_repo.get_transcript(sid, USER.user_id)
        assert completed is not None
        assert [message.role for message in completed.messages] == ["user", "assistant"]
        assert completed.messages[1].job_id == job_id
        assert completed.messages[1].content == "已完成，可在结果区查看。"

    asyncio.run(_impl())


def test_confirm_does_not_emit_job_started_when_anchor_write_fails(
    tmp_path, monkeypatch
) -> None:
    async def _impl() -> None:
        inf = await _infra(str(tmp_path))
        uid = await _stage(inf)
        orch = inf.orch(StubTextLLM(("", _gen_tc(uid, n=1))))
        planned = await _drain(orch.handle_message(USER, None, "生成一张图", [uid]))
        session_id = _first(planned, "session")["session_id"]
        token = _first(planned, "generation_confirm")["confirm_token"]

        async def fail_anchor(**_kwargs: object) -> str:
            raise RuntimeError("anchor write failed")

        monkeypatch.setattr(inf.chat_repo, "append_message", fail_anchor)
        stream = orch.handle_confirm(USER, session_id, token, "confirm")
        first = await anext(stream)
        assert first.type == "session"
        with pytest.raises(RuntimeError, match="anchor write failed"):
            await anext(stream)

    asyncio.run(_impl())


def test_4k_confirm_launches_with_pending_model_snapshot(tmp_path) -> None:
    async def _impl() -> None:
        inf = await _infra(str(tmp_path))
        uid = await _stage(inf)
        orch = inf.orch(StubTextLLM(("", _gen_tc(uid, n=1))))
        planned = await _drain(orch.handle_message(USER, None, "生成一张 4K 主图", [uid]))
        session_id = _first(planned, "session")["session_id"]
        token = _first(planned, "generation_confirm")["confirm_token"]

        confirmed = await _drain(orch.handle_confirm(USER, session_id, token, "confirm"))

        assert inf.submission.calls == ["gpt-image-2"]
        assert "job_started" in [event_type for event_type, _data in confirmed]

    asyncio.run(_impl())


def test_confirm_rechecks_model_disabled_after_cost_card(tmp_path) -> None:
    async def _impl() -> None:
        inf = await _infra(str(tmp_path))
        uid = await _stage(inf)
        orch = inf.orch(StubTextLLM(("", _gen_tc(uid, n=1))))
        planned = await _drain(orch.handle_message(USER, None, "生成一张 4K 主图", [uid]))
        session_id = _first(planned, "session")["session_id"]
        token = _first(planned, "generation_confirm")["confirm_token"]
        inf.model_config.set_enabled("gpt-image-2", False)

        confirmed = await _drain(orch.handle_confirm(USER, session_id, token, "confirm"))

        assert _first(confirmed, "error")["code"] == "model_unavailable"
        assert inf.submission.calls == []
        assert await inf.chat_repo.job_count(session_id) == 0

    asyncio.run(_impl())


def test_editing_a_4k_source_uses_only_the_current_turn_for_model_selection(
    tmp_path,
) -> None:
    async def _impl() -> None:
        inf = await _infra(str(tmp_path))
        uid = await _stage(inf)
        edit_call = (
            ToolCall(
                id="edit-1",
                name="edit",
                arguments={
                    "source_image_key": "model-guessed.png",
                    "prompt": "把背景改成蓝色",
                    "edit_mode": "delta",
                },
            ),
        )
        orch = inf.orch(
            StubTextLLM(
                ("", _gen_tc(uid, n=1)),
                ("", edit_call),
                ("", edit_call),
            )
        )
        generated = await _drain(orch.handle_message(USER, None, "生成一张 4K 主图", [uid]))
        session_id = _first(generated, "session")["session_id"]
        confirmed = await _drain(
            orch.handle_confirm(
                USER,
                session_id,
                _first(generated, "generation_confirm")["confirm_token"],
                "confirm",
            )
        )
        detail = await inf.query.get_job(
            job_id=_first(confirmed, "job_started")["job_id"],
            user_id=USER.user_id,
        )
        assert detail is not None
        source_image_key = detail.images[0].image_key

        standard_edit = await _drain(
            orch.handle_message(
                USER,
                session_id,
                "把背景改成蓝色",
                [],
                edit_source_image_key=source_image_key,
            )
        )
        _first(standard_edit, "generation_confirm")
        assert inf.pending._pending[session_id].image_model == "gpt-image-2"

        four_k_edit = await _drain(
            orch.handle_message(
                USER,
                session_id,
                "继续改成蓝色，保持 4K",
                [],
                edit_source_image_key=source_image_key,
            )
        )
        four_k_confirm = _first(four_k_edit, "generation_confirm")
        assert four_k_confirm["args"]["ratio"] == "16:9"
        assert four_k_confirm["args"]["edit_mode"] == "full"
        assert inf.pending._pending[session_id].image_model == "gpt-image-2"

    asyncio.run(_impl())


def test_confirm_token_is_one_time(tmp_path) -> None:
    async def _impl() -> None:
        inf = await _infra(str(tmp_path))
        uid = await _stage(inf)
        orch = inf.orch(StubTextLLM(("", _gen_tc(uid, n=1))))
        msg = await _drain(orch.handle_message(USER, None, "出一张", [uid]))
        sid = _first(msg, "session")["session_id"]
        tok = _first(msg, "generation_confirm")["confirm_token"]
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
        tok = _first(msg, "generation_confirm")["confirm_token"]
        canc = await _drain(orch.handle_confirm(USER, sid, tok, "cancel"))
        assert not any(t == "job_started" for t, _ in canc)
        assert canc[-1] == ("assistant_end", {"status": "complete"})
        after = await _drain(orch.handle_confirm(USER, sid, tok, "confirm"))
        assert any(t == "error" and d["code"] == "invalid_confirm_token" for t, d in after)
        assert inf.submission.calls == []
        assert await inf.chat_repo.job_count(sid) == 0

    asyncio.run(_impl())


def test_cancel_with_stale_token_preserves_current_pending(tmp_path) -> None:
    async def _impl() -> None:
        inf = await _infra(str(tmp_path))
        uid = await _stage(inf)
        orch = inf.orch(StubTextLLM(("", _gen_tc(uid, n=1))))
        planned = await _drain(orch.handle_message(USER, None, "出一张", [uid]))
        session_id = _first(planned, "session")["session_id"]
        token = _first(planned, "generation_confirm")["confirm_token"]

        stale_cancel = await _drain(orch.handle_confirm(USER, session_id, "ct_stale", "cancel"))
        assert _first(stale_cancel, "error")["code"] == "invalid_confirm_token"
        assert inf.pending._pending[session_id].confirm_token == token

        confirmed = await _drain(orch.handle_confirm(USER, session_id, token, "confirm"))
        assert "job_started" in [event_type for event_type, _data in confirmed]

    asyncio.run(_impl())


def test_session_job_limit_blocks_second_confirm(tmp_path) -> None:
    async def _impl() -> None:
        inf = await _infra(str(tmp_path), max_session_jobs=1)
        uid = await _stage(inf)
        orch = inf.orch(StubTextLLM(("", _gen_tc(uid, n=1))))
        m1 = await _drain(orch.handle_message(USER, None, "出一张", [uid]))
        sid = _first(m1, "session")["session_id"]
        tok1 = _first(m1, "generation_confirm")["confirm_token"]
        c1 = await _drain(orch.handle_confirm(USER, sid, tok1, "confirm"))
        assert any(t == "job_started" for t, _ in c1)
        m2 = await _drain(orch.handle_message(USER, sid, "再出一张", [uid]))
        tok2 = _first(m2, "generation_confirm")["confirm_token"]
        c2 = await _drain(orch.handle_confirm(USER, sid, tok2, "confirm"))
        assert any(t == "error" and d["code"] == "session_job_limit" for t, d in c2)
        assert not any(t == "job_started" for t, _ in c2)

    asyncio.run(_impl())


def test_placeholder_model_ratio_is_overridden_by_deterministic_ratio(tmp_path) -> None:
    async def _impl() -> None:
        inf = await _infra(str(tmp_path))
        uid = await _stage(inf)
        # 真 LLM 偶把问题填进 ratio，后端用确定比例覆盖，不让占位文本进入费用卡。
        orch = inf.orch(StubTextLLM(("好的", _gen_tc(uid, ratio="请问你要什么比例?", n=1))))
        ev = await _drain(orch.handle_message(USER, None, "出图", [uid]))
        assert _first(ev, "tool_call")["args"]["ratio"] == "1:1"
        assert _first(ev, "generation_confirm")["args"]["ratio"] == "1:1"
        assert ev[-1] == ("assistant_end", {"status": "awaiting_confirm"})

    asyncio.run(_impl())


def test_validation_clarification_hides_internal_field_names(tmp_path) -> None:
    """P3-#5：校验失败转澄清的用户文案=话术，不吐 upload_ids 等内部字段名。"""

    async def _impl() -> None:
        inf = await _infra(str(tmp_path))
        # LLM 产 upload_ids=[] 的 generate（漏带产品图）→ validate 失败 → 澄清而非报错
        bad = (
            ToolCall(
                id="c1",
                name="generate",
                arguments={"upload_ids": [], "prompt": "花生", "ratio": "1:1", "n": 1},
            ),
        )
        orch = inf.orch(StubTextLLM(("好的", bad)))
        ev = await _drain(orch.handle_message(USER, None, "出图", []))
        types = [t for t, _ in ev]
        assert "generation_confirm" not in types and "tool_call" not in types
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
        assert "generation_confirm" not in types and "tool_call" not in types
        assert any(t == "assistant_delta" for t in types)
        assert ev[-1] == ("assistant_end", {"status": "complete"})

    asyncio.run(_impl())


# ── 持久化(ISSUE-0051 验收)：刷新不丢 / owner 404 / CASCADE 删 ─────────────────


def test_chat_repository_updates_the_same_assistant_message(tmp_path) -> None:
    async def _impl() -> None:
        inf = await _infra(str(tmp_path))
        session_id = uuid.uuid4().hex
        await inf.chat_repo.create_session(
            session_id=session_id,
            user_id=USER.user_id,
            title="恢复生图",
        )
        message_id = await inf.chat_repo.append_message(
            session_id=session_id,
            role="assistant",
            content="生图任务详情如下：",
            job_id="job-1",
        )

        await inf.chat_repo.update_assistant_message(
            session_id=session_id,
            message_id=message_id,
            content="已完成，可在结果区查看。",
        )

        transcript = await inf.chat_repo.get_transcript(session_id, USER.user_id)
        assert transcript is not None
        assert len(transcript.messages) == 1
        assert transcript.messages[0].content == "已完成，可在结果区查看。"
        assert transcript.messages[0].job_id == "job-1"

    asyncio.run(_impl())


def test_running_job_anchors_remain_isolated_between_sessions(tmp_path) -> None:
    async def _impl() -> None:
        inf = await _infra(str(tmp_path))
        session_a = uuid.uuid4().hex
        session_b = uuid.uuid4().hex
        await inf.chat_repo.create_session(
            session_id=session_a, user_id=USER.user_id, title="A"
        )
        await inf.chat_repo.create_session(
            session_id=session_b, user_id=USER.user_id, title="B"
        )
        await inf.chat_repo.append_message(
            session_id=session_a, role="assistant", content="任务 A", job_id="job-a"
        )
        await inf.chat_repo.append_message(
            session_id=session_b, role="assistant", content="任务 B", job_id="job-b"
        )

        transcript_a = await inf.chat_repo.get_transcript(session_a, USER.user_id)
        transcript_b = await inf.chat_repo.get_transcript(session_b, USER.user_id)
        assert transcript_a is not None and transcript_b is not None
        assert [message.job_id for message in transcript_a.messages] == ["job-a"]
        assert [message.job_id for message in transcript_b.messages] == ["job-b"]

    asyncio.run(_impl())


def test_transcript_persists_across_new_orchestrator(tmp_path) -> None:
    """验收①：会话与消息落库，新 orchestrator 实例(模拟刷新/重启)仍能回显。"""

    async def _impl() -> None:
        inf = await _infra(str(tmp_path))
        orch = inf.orch(StubTextLLM(("你好呀，需要出什么图？", ())))
        msg = await _drain(orch.handle_message(USER, None, "你好", []))
        sid = _first(msg, "session")["session_id"]
        # 新 orchestrator + 全新 PendingStore(内存态丢失)，共享同一 DB
        inf2 = Infra(
            inf.submission,
            inf.uploads,
            inf.events,
            inf.chat_repo,
            PendingStore(),
            inf.query,
            inf.model_config,
            inf.max_session_jobs,
            inf.reverse_prompt,
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


# ── ListingSubmissionService.validate 纯校验(#884⑤ 与出图同一校验源) ─────────


def test_validate_rejects_bad_ratio(tmp_path) -> None:
    async def _impl() -> None:
        inf = await _infra(str(tmp_path))
        uid = await _stage(inf)
        req = ListingGenerateRequest(
            image_model="gpt-image-2", upload_ids=[uid], prompt="p", ratio="21:9", n=1
        )
        with pytest.raises(ValueError):
            inf.submission.validate(USER.user_id, req)

    asyncio.run(_impl())


def test_validate_rejects_non_owned_upload(tmp_path) -> None:
    async def _impl() -> None:
        inf = await _infra(str(tmp_path))
        req = ListingGenerateRequest(
            image_model="gpt-image-2",
            upload_ids=["deadbeef0000/x.png"],
            prompt="p",
            ratio="1:1",
            n=1,
        )
        with pytest.raises(NotFoundError):
            inf.submission.validate(USER.user_id, req)

    asyncio.run(_impl())


def test_validate_clone_requires_one_product(tmp_path) -> None:
    async def _impl() -> None:
        inf = await _infra(str(tmp_path))
        req = CloneRequest(
            image_model="gpt-image-2",
            product_upload_ids=[],
            reference_upload_ids=["a"],
            clone_mode="参考风格",
            ratio="1:1",
        )
        with pytest.raises(ValueError):
            inf.submission.validate(USER.user_id, req)

    asyncio.run(_impl())


def test_validate_edit_delta_rejects_ratio(tmp_path) -> None:
    async def _impl() -> None:
        inf = await _infra(str(tmp_path))
        req = EditRequest(
            image_model="gpt-image-2",
            source_image_key="k",
            prompt="改暖色",
            edit_mode="delta",
            ratio="1:1",
        )
        with pytest.raises(ValueError):
            inf.submission.validate(USER.user_id, req)

    asyncio.run(_impl())


# ── PendingStore：confirm_token 一次性 / 过期 / clear ─────────────────────────


def _req() -> ListingGenerateRequest:
    return ListingGenerateRequest(
        image_model="gpt-image-2", upload_ids=["a"], prompt="p", ratio="1:1", n=1
    )


def test_pending_take_one_time_and_mismatch_preserves() -> None:
    p = PendingStore()
    action = p.new(
        "s1",
        tool="generate",
        req=_req(),
        count=1,
        chat_model="doubao-chat",
        image_model="gpt-image-2",
        model_display_name="GPT Image 2.0",
        render_tier=RenderTier.FOUR_K,
    )
    assert action.image_model == "gpt-image-2"
    assert p.take("s1", "wrong") is None  # 不匹配不消费
    assert p.take("s1", action.confirm_token) is action  # 真 token 仍在
    assert p.take("s1", action.confirm_token) is None  # 一次性，二次拒


def test_pending_take_expired() -> None:
    p = PendingStore(ttl_seconds=-1.0)  # 立即过期
    action = p.new(
        "s1",
        tool="generate",
        req=_req(),
        count=1,
        chat_model="doubao-chat",
        image_model="gpt-image-2",
        model_display_name="GPT Image 2.0",
        render_tier=RenderTier.STANDARD,
    )
    assert p.take("s1", action.confirm_token) is None  # 匹配但过期
    assert p.take("s1", action.confirm_token) is None  # 已消费


def test_pending_clear() -> None:
    p = PendingStore()
    action = p.new(
        "s1",
        tool="generate",
        req=_req(),
        count=1,
        chat_model="doubao-chat",
        image_model="gpt-image-2",
        model_display_name="GPT Image 2.0",
        render_tier=RenderTier.STANDARD,
    )
    p.clear("s1")
    assert p.take("s1", action.confirm_token) is None


# ── A3 工具化：读工具（query_my_jobs/get_job_recipe/get_pricing_quota）验收⑥ ──


def test_read_tool_loop_executes_and_feeds_back(tmp_path) -> None:
    """读工具即时执行→结果回喂→LLM 收尾；不进费用闸（写工具才过闸）。"""

    async def _impl() -> None:
        inf = await _infra(str(tmp_path))
        tc = (ToolCall(id="q1", name="query_my_jobs", arguments={}),)
        llm = StubTextLLM(("", tc), ("你最近还没出过图哦。", ()))
        orch = inf.orch(llm)
        ev = await _drain(orch.handle_message(USER, None, "我最近出过什么图", []))
        types = [t for t, _ in ev]
        assert "generation_confirm" not in types and "tool_call" not in types  # 读工具不花钱不过闸
        assert any(t == "step" and d.get("phase") == "querying" for t, d in ev)
        text = "".join(d.get("text", "") for t, d in ev if t == "assistant_delta")
        assert "还没出过图" in text  # LLM 基于工具结果收尾
        assert ev[-1] == ("assistant_end", {"status": "complete"})
        session_id = next(data["session_id"] for event, data in ev if event == "session")
        assert llm.contexts == [
            ModelCallContext(
                user_id=USER.user_id,
                operation=ModelOperation.CHAT_COMPLETION,
                chat_session_id=session_id,
            ),
            ModelCallContext(
                user_id=USER.user_id,
                operation=ModelOperation.CHAT_COMPLETION,
                chat_session_id=session_id,
            ),
        ]

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
        tok = _first(msg, "generation_confirm")["confirm_token"]
        await _drain(orch.handle_confirm(USER, sid, tok, "confirm"))
        mine = await inf.orch(StubTextLLM(("", ())))._tool_query_my_jobs(USER, {})
        assert "job_id=" in mine and "暂无出图记录" not in mine
        theirs = await inf.orch(StubTextLLM(("", ())))._tool_query_my_jobs(OTHER, {})
        assert "暂无出图记录" in theirs  # 他人查不到本人的单

    asyncio.run(_impl())
