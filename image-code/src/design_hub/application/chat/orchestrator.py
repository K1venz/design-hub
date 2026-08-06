"""ChatOrchestrator（方案 C 零框架 tool-use 循环 + 对话历史持久化 ISSUE-0051）。

多轮澄清 → LLM 产结构化 tool_call（= /listing 请求体字段，绝不直出图像 prompt，铁律①）
→ 费用确认闸（暂停）→ 用户确认 → 经 ListingSubmissionService 走同一可靠任务链
→ 转发 job SSE（包一层 job_event）→ 收尾话术。

转录持久化（取舍①）：user 消息 + assistant 最终答复(+job_id) 落 ChatSessionRepository；
过程态（流式吐字/步骤/费用卡/tool_call）不落库。LLM 多轮上下文每轮从 DB 转录重建（刷新/
重启可续）。confirm_token 留内存（PendingStore，取舍⑤）。产出 ChatEvent 流由 /chat 路由序列化 SSE。
"""

import logging
import uuid
from collections import Counter
from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from typing import Any

from structlog.contextvars import get_contextvars

from design_hub.application.chat.image_options import ChatImageOptions
from design_hub.application.chat.image_ratio import detect_supported_ratio
from design_hub.application.chat.pending_store import PendingAction, PendingStore
from design_hub.application.chat.ratio_intent import (
    ChatRatioDecision,
    UnsupportedChatRatio,
)
from design_hub.application.chat.rendering_intent import (
    ChatRenderingDecision,
    decide_chat_ratio_note,
    decide_chat_rendering,
)
from design_hub.application.chat.system_prompt import default_system_prompt
from design_hub.application.chat.tool_requests import (
    ChatCloneRequest,
    ChatEditRequest,
    ChatGenerateRequest,
    ChatOpenFeatureRequest,
)
from design_hub.application.image_prompts.reverse_prompt import (
    ReversePromptRequest,
    ReversePromptService,
    format_reverse_prompt,
)
from design_hub.application.listing.requests import (
    BackgroundReplaceRequest,
    CloneRequest,
    EditRequest,
    ListingGenerateRequest,
)
from design_hub.application.listing.submission_service import (
    ListingSubmissionService,
)
from design_hub.application.listing.upload_service import UploadService
from design_hub.application.tasking.health import (
    AdmissionRejected,
    RedisUnavailable,
)
from design_hub.domain.admin import ModelOperation
from design_hub.domain.enums import ModelType, TaskEventType
from design_hub.domain.errors import DomainError, NotFoundError
from design_hub.domain.models import AuthUser, ChatTranscript
from design_hub.domain.tasking import RenderTier
from design_hub.ports.chat_repository import ChatSessionRepository
from design_hub.ports.events import ReplayableEventStream
from design_hub.ports.generation_work import IdempotencyConflict
from design_hub.ports.listing_query import ListingHistoryQuery
from design_hub.ports.model_calls import ModelCallContext
from design_hub.ports.model_config_repository import ModelConfigRepository
from design_hub.ports.model_resolution import (
    ModelUnavailableError,
    TextLLMResolver,
)
from design_hub.ports.text_llm import (
    ChatMessage,
    TextChunk,
    TextLLMError,
    ToolCall,
    ToolSpec,
)
from design_hub.ports.upload_store import UploadReadError, owns

logger = logging.getLogger(__name__)

# 长会话上下文裁剪（A3）：LLM 上下文超此消息数 → 只带首条(原始诉求) + 最近若干；
# DB 转录仍全量存，仅裁 LLM 输入控 token/成本。约 20 轮 user+assistant ≈ 40 条。
_CONTEXT_MAX_MESSAGES = 40
_CONTEXT_HEAD = 1
@dataclass(frozen=True)
class ChatEvent:
    """对话流事件（路由序列化为 SSE：event: <type>\\ndata: <json>）。"""

    type: str
    data: dict[str, Any]


# 工具化架构（A3）：写/花钱工具过费用闸（护栏①）；读工具即时执行、owner-scoped（护栏③）。
_WRITE_TOOLS = frozenset(
    {"generate", "clone", "edit", "replace_background"}
)
_READ_TOOLS = frozenset({"query_my_jobs", "get_job_recipe"})
_MAX_TOOL_ITERS = 5  # 读工具回喂循环上限（防 LLM 无限调工具）


def _tool_specs() -> list[ToolSpec]:
    # 工具参数 schema 直接取自请求 DTO（单一事实源，与提交服务校验同源）。
    # description 强调「信息齐全才调用、缺必填先追问、别把占位问句填进参数」（A3 降残余风险）。
    return [
        ToolSpec(
            "generate",
            "出图（单图流 n 或套图 plan）。拿到产品图 upload_ids 且用户意图可执行时调用；"
            "确定比例由系统备注提供，调用时必须原样使用。未明确套图或张数时按单图 n=1，"
            "不要为比例或张数追问。",
            ChatGenerateRequest.model_json_schema(),
        ),
        ToolSpec(
            "clone",
            "爆款图复刻。需产品图 1 张 + 爆款参考图 1..2 张 + clone_mode；未集齐先追问、不要调用。",
            ChatCloneRequest.model_json_schema(),
        ),
        ToolSpec(
            "edit",
            "二次编辑已产出的图。需 source_image_key + 编辑指令；用户未明确要改哪张/怎么改先追问。",
            ChatEditRequest.model_json_schema(),
        ),
        ToolSpec(
            "replace_background",
            "专用换背景。需要一张商品源图，以及背景文字描述或背景参考图。"
            "适合主体清晰、背景可分离的商品图；包装文字尽量保留，但不能保证像素级保真，"
            "大面积海报文案和复杂排版可能变化。该边界不增加额外确认："
            "信息完整且用户明确要求执行时直接调用；不要改用通用 edit，也不要引导用户跳页面。",
            BackgroundReplaceRequest.model_json_schema(),
        ),
        ToolSpec(
            "reverse_prompt",
            "分析一张上传图或平台生成图，返回结构化画面分析和中英文重建提示词。"
            "用户明确要求反推提示词时调用；不产生图片、不走费用确认。",
            ReversePromptRequest.model_json_schema(),
        ),
        ToolSpec(
            "open_feature",
            "仅当用户主动要求打开页面，或明确需要在页面精细调整换背景参数时调用。"
            "信息完整且用户要求直接换背景时不得调用。",
            ChatOpenFeatureRequest.model_json_schema(),
        ),
        ToolSpec(
            "query_my_jobs",
            "查询当前用户自己的出图历史（最近若干单、可按状态筛）。用户问「我出过什么图/上次那单」时用。",
            {
                "type": "object",
                "properties": {
                    "limit": {"type": "integer", "description": "返回条数，默认 5、上限 10"},
                    "status": {"type": "string", "description": "可选状态筛：完成/部分完成/失败"},
                },
            },
        ),
        ToolSpec(
            "get_job_recipe",
            "查某一单的配方（比例/图型配比/风格描述/平台），用于「用上次配置再来一套」。"
            "需 job_id（可先用 query_my_jobs 拿）。取到配方后要再出图仍需调 generate、走费用确认。",
            {
                "type": "object",
                "properties": {"job_id": {"type": "string"}},
                "required": ["job_id"],
            },
        ),
    ]


def _title(message: str) -> str:
    text = message.strip().replace("\n", " ")
    return (text[:40] or "新对话")


def _to_llm_messages(
    transcript: ChatTranscript,
    *,
    current_ratio: ChatRatioDecision | None = None,
    edit_source_image_key: str | None = None,
) -> list[ChatMessage]:
    """从 DB 转录重建 LLM 上下文；带附图的 user 消息注回 upload_ids 备注（不入持久转录）。

    长会话裁剪（A3）：超 _CONTEXT_MAX_MESSAGES 条 → 首条(原始诉求) + 最近若干 + 一行省略备注，
    控 token/成本；DB 转录本身仍全量存（get_transcript 不变）。
    """
    out: list[ChatMessage] = []
    for m in transcript.messages:
        content = m.content
        if m.role == "user" and m.attachment_upload_ids:
            note = ",".join(m.attachment_upload_ids)
            content = f"{content}\n\n[系统备注] 本轮可用产品图 upload_ids={note}"
        out.append(ChatMessage(role=m.role, content=content))
    notes: list[str] = []
    if current_ratio is not None:
        if current_ratio.ratio is None:
            notes.append(
                f"[系统备注] 用户明确要求比例={current_ratio.requested}，当前不支持；"
                "若用户明确要出图，不要调用写工具，告知支持的五种比例。"
            )
        else:
            notes.append(
                f"[系统备注] 本轮确定比例={current_ratio.ratio}，"
                f"来源={current_ratio.source.value}。调用 generate/clone 时必须原样使用。"
            )
    if edit_source_image_key is not None:
        notes.append(
            "[系统备注] 用户已通过界面明确选定编辑底图 "
            f"source_image_key={edit_source_image_key}。若本轮要求修改图片，必须调用 edit "
            "并原样使用此 key；不得改用 generate 或猜测其他底图。"
        )
    if notes:
        if not out or out[-1].role != "user":
            raise ValueError("本轮系统备注只能注入当前 user 消息")
        current = out[-1]
        out[-1] = ChatMessage(
            role=current.role,
            content=f"{current.content}\n\n" + "\n".join(notes),
            tool_call_id=current.tool_call_id,
            tool_calls=current.tool_calls,
        )
    if len(out) <= _CONTEXT_MAX_MESSAGES:
        return out
    elided = ChatMessage(
        role="user", content="[系统备注] 为控制长度，中间若干轮对话已省略，以下为最近对话。"
    )
    return [*out[:_CONTEXT_HEAD], elided, *out[_CONTEXT_HEAD - _CONTEXT_MAX_MESSAGES :]]


@dataclass
class ChatOrchestrator:
    text_llm_resolver: TextLLMResolver
    submission: ListingSubmissionService
    event_stream: ReplayableEventStream
    uploads: UploadService
    chat_repo: ChatSessionRepository
    pending: PendingStore
    query: ListingHistoryQuery  # 读工具：出图历史/配方（owner-scoped，护栏③）
    model_config: ModelConfigRepository
    reverse_prompt: ReversePromptService
    max_session_jobs: int = 5  # 会话级出图闸（#884②）
    # 四段 system prompt（persona/知识库/工具契约/守则，A3）：启动组装缓存，可注入便于测试
    system_prompt: str = field(default_factory=default_system_prompt)
    _tools: list[ToolSpec] = field(default_factory=_tool_specs)

    async def _auto_ratio(self, user: AuthUser, upload_ids: list[str]) -> str:
        if not upload_ids or not owns(upload_ids[0], user.user_id):
            return "1:1"
        try:
            data, _content_type = await self.uploads.load(upload_ids[0])
        except (ValueError, NotFoundError, UploadReadError):
            return "1:1"
        return detect_supported_ratio(data)

    async def handle_message(
        self,
        user: AuthUser,
        session_id: str | None,
        message: str,
        upload_ids: list[str],
        *,
        chat_model: str,
        image_model: str,
        image_options: ChatImageOptions,
        edit_source_image_key: str | None = None,
    ) -> AsyncIterator[ChatEvent]:
        if session_id is None:
            session_id = uuid.uuid4().hex
            await self.chat_repo.create_session(
                session_id=session_id, user_id=user.user_id, title=_title(message)
            )
        elif not await self.chat_repo.session_owned(session_id, user.user_id):
            yield ChatEvent("error", {"code": "bad_request", "message": "会话不存在或无权访问"})
            yield ChatEvent("assistant_end", {"status": "error"})
            return
        yield ChatEvent("session", {"session_id": session_id})
        self.pending.clear(session_id)  # 新消息作废旧 pending（重新规划）

        # 落 user 消息（原始文本 + 附图；[系统备注] 是重建 LLM 上下文时注回，不入持久转录）
        await self.chat_repo.append_message(
            session_id=session_id, role="user", content=message,
            attachment_upload_ids=tuple(upload_ids),
        )
        transcript = await self.chat_repo.get_transcript(session_id, user.user_id)
        assert transcript is not None  # 刚 owner-check + append，必存在
        auto_ratio = await self._auto_ratio(user, upload_ids)
        ratio_decision = decide_chat_ratio_note(message, auto_ratio, image_options)
        llm_messages = [
            ChatMessage(role="system", content=self.system_prompt),
            *_to_llm_messages(
                transcript,
                current_ratio=ratio_decision,
                edit_source_image_key=edit_source_image_key,
            ),
        ]
        llm_context = ModelCallContext(
            user_id=user.user_id,
            operation=ModelOperation.CHAT_COMPLETION,
            chat_session_id=session_id,
        )

        # 工具化 tool-use 循环（A3）：读工具即时执行→结果回喂→再问 LLM；写工具→费用闸；纯文本→收尾。
        for _ in range(_MAX_TOOL_ITERS):
            assistant_text = ""
            assistant_chunks: list[str] = []
            tool_calls: tuple[ToolCall, ...] = ()
            llm_failed = False
            llm_error_code = "llm_unavailable"
            logger.info(
                "chat_model_started",
                extra={
                    "chain": "chat",
                    "action": "开始调用对话模型",
                    "operation_id": session_id,
                    "status": "started",
                },
            )
            try:
                text_llm = await self.text_llm_resolver.resolve(
                    chat_model,
                    ModelType.CHAT,
                )
                async for chunk in text_llm.complete(
                    context=llm_context,
                    messages=llm_messages,
                    tools=self._tools,
                ):
                    if isinstance(chunk, TextChunk):
                        assistant_text += chunk.text
                        assistant_chunks.append(chunk.text)
                    else:
                        tool_calls = chunk.tool_calls
            except ModelUnavailableError:
                logger.warning(
                    "chat_model_unavailable",
                    extra={
                        "chain": "chat",
                        "action": "对话模型未启用",
                        "operation_id": session_id,
                        "status": "unavailable",
                    },
                )
                llm_failed = True
                llm_error_code = "model_unavailable"
            except TextLLMError:
                logger.error(
                    "chat_model_failed",
                    extra={
                        "chain": "chat",
                        "action": "对话模型调用失败",
                        "operation_id": session_id,
                        "status": "failed",
                    },
                    exc_info=True,
                )
                llm_failed = True
            if llm_failed:
                for text in assistant_chunks:
                    yield ChatEvent("assistant_delta", {"text": text})
                if assistant_chunks:
                    await self.chat_repo.append_message(
                        session_id=session_id,
                        role="assistant",
                        content=assistant_text,
                    )
                yield ChatEvent(
                    "error",
                    {
                        "code": llm_error_code,
                        "message": "当前文本模型已不可用，请重新选择。"
                        if llm_error_code == "model_unavailable"
                        else "对话模型暂时不可用",
                    },
                )
                yield ChatEvent("assistant_end", {"status": "error"})
                return
            logger.info(
                "chat_model_completed",
                extra={
                    "chain": "chat",
                    "action": "对话模型调用完成",
                    "operation_id": session_id,
                    "status": "completed",
                },
            )

            if not tool_calls:  # 纯文本（澄清/答复/顾问建议）：落 assistant 转录，收尾
                for text in assistant_chunks:
                    yield ChatEvent("assistant_delta", {"text": text})
                await self.chat_repo.append_message(
                    session_id=session_id, role="assistant", content=assistant_text
                )
                yield ChatEvent("assistant_end", {"status": "complete"})
                return

            call = tool_calls[0]  # MVP：一轮一工具
            if call.name == "reverse_prompt":
                yield ChatEvent(
                    "step",
                    {"phase": "analyzing", "detail": "正在分析图片"},
                )
                try:
                    reverse_request = ReversePromptRequest.model_validate(
                        call.arguments
                    )
                    reverse_result = await self.reverse_prompt.reverse(
                        user_id=user.user_id,
                        request=reverse_request,
                    )
                except (
                    ValueError,
                    NotFoundError,
                    TextLLMError,
                    UploadReadError,
                ) as exc:
                    text = f"暂时无法反推这张图：{exc}"
                    yield ChatEvent("assistant_delta", {"text": text})
                    await self.chat_repo.append_message(
                        session_id=session_id,
                        role="assistant",
                        content=text,
                    )
                    yield ChatEvent(
                        "assistant_end",
                        {"status": "complete"},
                    )
                    return
                rendered = format_reverse_prompt(reverse_result)
                yield ChatEvent("assistant_delta", {"text": rendered})
                await self.chat_repo.append_message(
                    session_id=session_id,
                    role="assistant",
                    content=rendered,
                )
                yield ChatEvent("assistant_end", {"status": "complete"})
                return

            if call.name == "open_feature":
                try:
                    feature_request = ChatOpenFeatureRequest.model_validate(
                        call.arguments
                    )
                    await self._validate_feature_prefill(
                        user,
                        feature_request,
                    )
                except (ValueError, NotFoundError, UploadReadError) as exc:
                    text = f"暂时无法打开这个功能：{exc}"
                    yield ChatEvent("assistant_delta", {"text": text})
                    await self.chat_repo.append_message(
                        session_id=session_id,
                        role="assistant",
                        content=text,
                    )
                    yield ChatEvent(
                        "assistant_end",
                        {"status": "complete"},
                    )
                    return
                text = "已为你填好现有信息，可以进入换背景工作台继续调整。"
                yield ChatEvent("assistant_delta", {"text": text})
                yield ChatEvent(
                    "action_card",
                    self._feature_action_card(feature_request),
                )
                await self.chat_repo.append_message(
                    session_id=session_id,
                    role="assistant",
                    content=text,
                )
                yield ChatEvent("assistant_end", {"status": "complete"})
                return

            if call.name in _READ_TOOLS:  # 读工具：owner-scoped 即时执行回喂（护栏③；不落库）
                for text in assistant_chunks:
                    yield ChatEvent("assistant_delta", {"text": text})
                yield ChatEvent("step", {"phase": "querying", "detail": "正在查询"})
                result = await self._run_read_tool(user, call)
                llm_messages.append(
                    ChatMessage(role="assistant", content=assistant_text, tool_calls=(call,))
                )
                llm_messages.append(
                    ChatMessage(role="tool", content=result, tool_call_id=call.id)
                )
                continue

            # 写工具（generate/clone/edit）→ 费用闸（护栏①：不给 LLM 绕闸的路）
            yield ChatEvent("step", {"phase": "planning", "detail": "正在规划出图参数"})
            try:
                rendering = decide_chat_rendering(message, auto_ratio, image_options)
                rendering = ChatRenderingDecision(
                    rendering.render_tier,
                    image_options.resolve_ratio_for(
                        model_id=image_model,
                        render_tier=rendering.render_tier,
                        decision=rendering.ratio,
                    ),
                )
                normalized_args = self._prepare_write_args(
                    call.name,
                    call.arguments,
                    rendering.ratio,
                    edit_source_image_key,
                    image_options.count,
                )
            except UnsupportedChatRatio as exc:
                clar = str(exc)
                yield ChatEvent("assistant_delta", {"text": clar})
                await self.chat_repo.append_message(
                    session_id=session_id, role="assistant", content=clar
                )
                yield ChatEvent("assistant_end", {"status": "complete"})
                return
            except ValueError as exc:
                clar = str(exc)
                yield ChatEvent("assistant_delta", {"text": clar})
                await self.chat_repo.append_message(
                    session_id=session_id, role="assistant", content=clar
                )
                yield ChatEvent("assistant_end", {"status": "complete"})
                return
            try:
                req = self._parse_req(
                    call.name,
                    normalized_args,
                    image_model,
                )
            except Exception:  # pydantic 校验失败（含 extra=forbid）：内部字段名不吐用户（P3-#5）
                clar = (
                    "这次出图参数还没整理完整，请确认已至少上传一张图片，"
                    "并直接告诉我想做什么，我马上重新安排。"
                )
                yield ChatEvent("assistant_delta", {"text": clar})
                await self.chat_repo.append_message(
                    session_id=session_id, role="assistant", content=clar
                )
                yield ChatEvent("assistant_end", {"status": "complete"})
                return
            count = self._count(call.name, req)
            try:
                image_options.validate_for(
                    model_id=image_model,
                    render_tier=rendering.render_tier,
                    resolved_ratio=rendering.ratio.require_supported(),
                    resolved_count=count,
                )
                # 与出图同一校验源（#884⑤/护栏②）：非法参数进费用闸前拦下转澄清；文案已是用户话术。
                if isinstance(req, BackgroundReplaceRequest):
                    await self.submission.validate_background_replace(
                        user_id=user.user_id,
                        request=req,
                    )
                else:
                    self.submission.validate(
                        user.user_id,
                        req,
                        render_tier=rendering.render_tier,
                    )
                config = await self.model_config.require_available_image(
                    image_model
                )
            except (DomainError, ValueError, NotFoundError) as exc:
                if str(exc) == "image model unavailable":
                    yield ChatEvent(
                        "error",
                        {
                            "code": "model_unavailable",
                            "message": "当前图片模型已不可用，请重新选择。",
                        },
                    )
                    yield ChatEvent("assistant_end", {"status": "error"})
                    return
                clar = f"还差点信息、暂时没法出图：{exc}。你补充一下，我再帮你安排～"
                yield ChatEvent("assistant_delta", {"text": clar})
                await self.chat_repo.append_message(
                    session_id=session_id, role="assistant", content=clar
                )
                yield ChatEvent("assistant_end", {"status": "complete"})
                return
            yield ChatEvent("tool_call", {"tool": call.name, "args": normalized_args})
            pending = self.pending.new(
                session_id,
                tool=call.name,
                req=req,
                count=count,
                chat_model=chat_model,
                image_model=config.name,
                model_display_name=config.display_name,
                render_tier=rendering.render_tier,
            )
            # assistant 最终答复（收尾语+job_id）留到 confirm 后落库；tool_call/cost_confirm 不落库
            yield ChatEvent(
                "generation_confirm",
                {
                    "confirm_token": pending.confirm_token,
                    "tool": call.name,
                    "args": normalized_args,
                    "count": count,
                    "image_model": config.name,
                    "model_display_name": config.display_name,
                    "render_tier": rendering.render_tier.value,
                    "ratio": rendering.ratio.require_supported(),
                },
            )
            yield ChatEvent("assistant_end", {"status": "awaiting_confirm"})
            return

        # 读工具回喂循环耗尽（LLM 反复调工具未收敛）→ 兜底收尾，防卡死
        fallback = "我查了下但还没完全理清，能再具体说说你想做什么吗？"
        yield ChatEvent("assistant_delta", {"text": fallback})
        await self.chat_repo.append_message(
            session_id=session_id, role="assistant", content=fallback
        )
        yield ChatEvent("assistant_end", {"status": "complete"})

    async def handle_confirm(
        self, user: AuthUser, session_id: str, confirm_token: str, action: str
    ) -> AsyncIterator[ChatEvent]:
        if not await self.chat_repo.session_owned(session_id, user.user_id):
            yield ChatEvent("error", {"code": "bad_request", "message": "会话不存在或无权访问"})
            yield ChatEvent("assistant_end", {"status": "error"})
            return
        yield ChatEvent("session", {"session_id": session_id})

        if action not in {"cancel", "confirm"}:
            yield ChatEvent("error", {"code": "bad_request", "message": f"未知 action：{action}"})
            yield ChatEvent("assistant_end", {"status": "error"})
            return

        pending = self.pending.take(session_id, confirm_token)
        if pending is None:
            yield ChatEvent(
                "error",
                {"code": "invalid_confirm_token", "message": "确认令牌无效或已过期，请重新发起。"},
            )
            yield ChatEvent("assistant_end", {"status": "error"})
            return

        if action == "cancel":
            yield ChatEvent("assistant_delta", {"text": "已取消本次出图。"})
            await self.chat_repo.append_message(
                session_id=session_id, role="assistant", content="已取消本次出图。"
            )
            yield ChatEvent("assistant_end", {"status": "complete"})
            return

        try:
            await self.model_config.require_available_image(
                pending.image_model
            )
        except DomainError:
            yield ChatEvent(
                "error",
                {
                    "code": "model_unavailable",
                    "message": self._model_unavailable_message(pending.render_tier),
                },
            )
            yield ChatEvent("assistant_end", {"status": "error"})
            return

        # 会话级闸（#884②）：启 job 前查（DB 派生 job_count，持久正确）
        if await self.chat_repo.job_count(session_id) >= self.max_session_jobs:
            yield ChatEvent(
                "error",
                {
                    "code": "session_job_limit",
                    "message": f"本次会话出图已达上限（{self.max_session_jobs} 单），请开新会话。",
                },
            )
            yield ChatEvent("assistant_end", {"status": "error"})
            return

        try:
            job_id = await self._launch(user, pending)
        except (
            ValueError,
            NotFoundError,
            DomainError,
            AdmissionRejected,
            RedisUnavailable,
            IdempotencyConflict,
        ) as exc:
            yield ChatEvent("error", {"code": self._err_code(exc), "message": str(exc)})
            yield ChatEvent("assistant_end", {"status": "error"})
            return
        plan = pending.req.plan if isinstance(pending.req, ListingGenerateRequest) else None
        yield ChatEvent(
            "job_started",
            {"job_id": job_id, "tool": pending.tool, "count": pending.count, "plan": plan},
        )

        completed = False
        cursor = "0-0"
        terminal = False
        while not terminal:
            deliveries = await self.event_stream.read(
                job_id=job_id,
                after_id=cursor,
                block_ms=15_000,
            )
            for delivery in deliveries:
                cursor = delivery.redis_id
                event = delivery.event
                yield ChatEvent(
                    "job_event",
                    {
                        "job_id": job_id,
                        "redis_id": delivery.redis_id,
                        "type": event.type.value,
                        "data": event.data,
                    },
                )
                if event.type == TaskEventType.TASK_COMPLETED:
                    completed = True
                    terminal = True
                elif event.type == TaskEventType.TASK_FAILED:
                    terminal = True

        # 收尾轮：从 DB 转录重建上下文 + 系统提示出图结果 → LLM 产自然收尾语（无工具）
        summary = "出图完成" if completed else "出图失败或部分失败"
        transcript = await self.chat_repo.get_transcript(session_id, user.user_id)
        note = ChatMessage(
            role="user",
            content=f"（系统提示）刚才的出图已{summary}，请用一句自然的话向用户收尾，不要再调用工具。",
        )
        history = _to_llm_messages(transcript) if transcript is not None else []
        llm_messages = [ChatMessage(role="system", content=self.system_prompt), *history, note]
        llm_context = ModelCallContext(
            user_id=user.user_id,
            operation=ModelOperation.CHAT_COMPLETION,
            chat_session_id=session_id,
        )
        closing = ""
        try:
            text_llm = await self.text_llm_resolver.resolve(
                pending.chat_model,
                ModelType.CHAT,
            )
            async for chunk in text_llm.complete(
                context=llm_context,
                messages=llm_messages,
                tools=[],
            ):
                if isinstance(chunk, TextChunk):
                    closing += chunk.text
                    yield ChatEvent("assistant_delta", {"text": chunk.text})
        except (ModelUnavailableError, TextLLMError):
            closing = "已完成，可在结果区查看。" if completed else "很抱歉，出图未成功，请重试。"
            yield ChatEvent("assistant_delta", {"text": closing})
        # 落 assistant 最终答复（+job_id，回显时 job_id→image_key→现签图，取舍②）
        await self.chat_repo.append_message(
            session_id=session_id, role="assistant", content=closing, job_id=job_id
        )
        yield ChatEvent("assistant_end", {"status": "complete"})

    async def _launch(self, user: AuthUser, pending: PendingAction) -> str:
        req = pending.req
        context = get_contextvars()
        request_id = context.get("request_id")
        if not isinstance(request_id, str) or not request_id:
            request_id = uuid.uuid4().hex
        trace_id = context.get("trace_id")
        if not isinstance(trace_id, str) or not trace_id:
            trace_id = request_id
        if pending.tool == "generate" and isinstance(req, ListingGenerateRequest):
            receipt = await self.submission.submit_generate(
                user_id=user.user_id,
                request=req,
                idempotency_key=pending.confirm_token,
                trace_id=trace_id,
                request_id=request_id,
                render_tier=pending.render_tier,
            )
            return receipt.job_id
        if pending.tool == "clone" and isinstance(req, CloneRequest):
            receipt = await self.submission.submit_clone(
                user_id=user.user_id,
                request=req,
                idempotency_key=pending.confirm_token,
                trace_id=trace_id,
                request_id=request_id,
                render_tier=pending.render_tier,
            )
            return receipt.job_id
        if pending.tool == "edit" and isinstance(req, EditRequest):
            receipt = await self.submission.submit_edit(
                user_id=user.user_id,
                request=req,
                idempotency_key=pending.confirm_token,
                trace_id=trace_id,
                request_id=request_id,
                render_tier=pending.render_tier,
            )
            return receipt.job_id
        if (
            pending.tool == "replace_background"
            and isinstance(req, BackgroundReplaceRequest)
        ):
            receipt = await self.submission.submit_background_replace(
                user_id=user.user_id,
                request=req,
                idempotency_key=pending.confirm_token,
                trace_id=trace_id,
                request_id=request_id,
                render_tier=pending.render_tier,
            )
            return receipt.job_id
        raise ValueError(f"未知工具：{pending.tool}")

    @staticmethod
    def _model_unavailable_message(render_tier: RenderTier) -> str:
        if render_tier is RenderTier.FOUR_K:
            return "4K 当前不可用，请取消 4K 后使用普通出图。"
        return "普通出图当前不可用，请稍后再试。"

    # ── 读工具（A3 工具化，owner-scoped 护栏③；不花钱、不过费用闸；结果回喂 LLM）──

    async def _run_read_tool(self, user: AuthUser, call: ToolCall) -> str:
        """派发读工具→文本结果（回喂 LLM）。异常兜底为文本，保持对话不中断（I/O 域）。"""
        try:
            if call.name == "query_my_jobs":
                return await self._tool_query_my_jobs(user, call.arguments)
            if call.name == "get_job_recipe":
                return await self._tool_get_job_recipe(user, call.arguments)
        except Exception:  # 读工具失败不炸对话：喂给 LLM 让它如实告知用户（不静默假装成功）
            return f"（{call.name} 查询暂时失败，请告知用户稍后再试，不要编造数据。）"
        return f"（未知查询工具 {call.name}。）"

    async def _tool_query_my_jobs(self, user: AuthUser, args: dict[str, Any]) -> str:
        limit = max(1, min(int(args.get("limit") or 5), 10))
        jobs = await self.query.list_jobs(
            user_id=user.user_id, limit=limit, offset=0, q=None
        )
        status = args.get("status")
        if status:
            jobs = [j for j in jobs if j.status == status]
        if not jobs:
            return "该用户暂无出图记录（owner-scoped，只查本人）。"
        lines = [f"该用户最近 {len(jobs)} 单（新→旧）："]
        lines += [
            f"- job_id={j.job_id} | {j.created_at:%Y-%m-%d %H:%M} | "
            f"平台={j.platform or '未指定'} | {j.n}张 | 状态={j.status}"
            for j in jobs
        ]
        return "\n".join(lines)

    async def _tool_get_job_recipe(self, user: AuthUser, args: dict[str, Any]) -> str:
        job_id = str(args.get("job_id") or "").strip()
        if not job_id:
            return "需要 job_id（可先用 query_my_jobs 查到）。"
        detail = await self.query.get_job(job_id=job_id, user_id=user.user_id)
        if detail is None:  # owner 隔离：非本人/不存在都返同一话术，不泄漏存在性
            return "找不到这单，或它不属于当前用户。"
        plan = Counter(im.image_type for im in detail.images if im.image_type)
        plan_str = "、".join(f"{t}×{c}" for t, c in plan.items()) or f"单图 {detail.n} 张"
        platform = (detail.modifiers or {}).get("platform", "未指定")
        return (
            f"这单（job_id={detail.job_id}）的配方（可复用）：\n"
            f"- 比例：{detail.ratio}\n- 图型配比：{plan_str}\n"
            f"- 风格描述：{detail.prompt}\n- 平台：{platform}\n"
            "要用这套配置再出一套，就用这些参数调 generate，并等待用户确认生成。"
        )

    @staticmethod
    def _prepare_write_args(
        tool: str,
        args: dict[str, Any],
        ratio: ChatRatioDecision,
        edit_source_image_key: str | None,
        count: int | None,
    ) -> dict[str, Any]:
        normalized = dict(args)
        if "image_model" in normalized:
            raise ValueError("模型只能使用本轮已选择的配置。")
        if tool != "generate" and count not in {None, 1}:
            raise ValueError(
                "当前操作一次只生成 1 张图片，请将数量设为 1 张或自适应。"
            )
        if tool == "replace_background":
            if ratio.changes_edit_ratio:
                raise ValueError(
                    "换背景会保持源图比例，请将比例设为自适应。"
                )
            return normalized
        if tool in {"generate", "clone"}:
            normalized["ratio"] = ratio.require_supported()
            if tool == "generate" and count is not None:
                normalized["n"] = count
                normalized.pop("plan", None)
            return normalized
        if tool != "edit":
            return normalized
        if edit_source_image_key is None:
            raise ValueError("请先在结果图上点击「继续编辑」，再告诉我需要怎么修改。")
        normalized["source_image_key"] = edit_source_image_key
        if ratio.changes_edit_ratio:
            normalized["edit_mode"] = "full"
            normalized["ratio"] = ratio.require_supported()
        else:
            normalized.pop("ratio", None)
        return normalized

    @staticmethod
    def _parse_req(
        tool: str, args: dict[str, Any], image_model: str
    ) -> (
        ListingGenerateRequest
        | CloneRequest
        | EditRequest
        | BackgroundReplaceRequest
    ):
        if tool == "generate":
            return ChatGenerateRequest(**args).to_listing(image_model)
        if tool == "clone":
            return ChatCloneRequest(**args).to_listing(image_model)
        if tool == "edit":
            return ChatEditRequest(**args).to_listing(image_model)
        if tool == "replace_background":
            return BackgroundReplaceRequest.model_validate(
                {**args, "image_model": image_model}
            )
        raise ValueError(f"未知工具：{tool}")

    @staticmethod
    def _count(
        tool: str,
        req: (
            ListingGenerateRequest
            | CloneRequest
            | EditRequest
            | BackgroundReplaceRequest
        ),
    ) -> int:
        if tool == "generate" and isinstance(req, ListingGenerateRequest):
            if req.n is not None:
                return req.n
            if req.plan is not None:
                return sum(req.plan.values())
        return 1

    async def _validate_feature_prefill(
        self,
        user: AuthUser,
        request: ChatOpenFeatureRequest,
    ) -> None:
        if request.source is not None:
            if request.source.kind == "upload":
                if not owns(request.source.upload_id, user.user_id):
                    raise NotFoundError("商品图不存在或无权访问")
                await self.uploads.load(request.source.upload_id)
            else:
                source = await self.query.resolve_generated_image_source(
                    source_image_key=request.source.image_key,
                    user_id=user.user_id,
                )
                if source is None:
                    raise NotFoundError("商品图不存在或无权访问")
        if (
            request.background is not None
            and request.background.kind == "reference"
        ):
            if not owns(request.background.upload_id, user.user_id):
                raise NotFoundError("背景图不存在或无权访问")
            await self.uploads.load(request.background.upload_id)

    @staticmethod
    def _feature_action_card(
        request: ChatOpenFeatureRequest,
    ) -> dict[str, Any]:
        prefill: dict[str, Any] = {}
        if request.source is not None:
            prefill["source_kind"] = request.source.kind
            prefill["source_id"] = (
                request.source.upload_id
                if request.source.kind == "upload"
                else request.source.image_key
            )
        if request.background is not None:
            prefill["background_kind"] = request.background.kind
            if request.background.kind == "description":
                prefill["background_description"] = (
                    request.background.description
                )
            else:
                prefill["background_reference_id"] = (
                    request.background.upload_id
                )
                if request.background.instruction:
                    prefill["background_instruction"] = (
                        request.background.instruction
                    )
        return {
            "feature": "background_replace",
            "label": "打开换背景工作台",
            "prefill": prefill,
        }

    @staticmethod
    def _err_code(exc: Exception) -> str:
        if isinstance(exc, (AdmissionRejected, RedisUnavailable)):
            return "generation_unavailable"
        if isinstance(exc, IdempotencyConflict):
            return "idempotency_conflict"
        return "bad_request"  # ValueError / NotFoundError
