"""ChatOrchestrator（方案 C 零框架 tool-use 循环 + 对话历史持久化 ISSUE-0051）。

多轮澄清 → LLM 产结构化 tool_call（= /listing 请求体字段，绝不直出图像 prompt，铁律①）
→ 费用确认闸（暂停）→ 用户确认 → 经 ListingJobLauncher 走同一出图链（频控/owner/
成本守卫/卡链全继承，#884⑤）→ 转发 job SSE（包一层 job_event）→ 收尾话术。

转录持久化（取舍①）：user 消息 + assistant 最终答复(+job_id) 落 ChatSessionRepository；
过程态（流式吐字/步骤/费用卡/tool_call）不落库。LLM 多轮上下文每轮从 DB 转录重建（刷新/
重启可续）。confirm_token 留内存（PendingStore，取舍⑤）。产出 ChatEvent 流由 /chat 路由序列化 SSE。
"""

import uuid
from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from typing import Any

from design_hub.application.chat.pending_store import PendingAction, PendingStore
from design_hub.application.chat.system_prompt import default_system_prompt
from design_hub.application.listing.job_launcher import ListingJobLauncher
from design_hub.application.listing.requests import (
    CloneRequest,
    EditRequest,
    ListingGenerateRequest,
)
from design_hub.application.rate_limit import RateLimited
from design_hub.application.registry import ProviderRegistry
from design_hub.domain.enums import ModelName, TaskEventType
from design_hub.domain.errors import BudgetExceeded, NotFoundError
from design_hub.domain.models import AuthUser, ChatTranscript
from design_hub.ports.chat_repository import ChatSessionRepository
from design_hub.ports.events import EventStream
from design_hub.ports.text_llm import (
    ChatMessage,
    TextChunk,
    TextLLMError,
    TextLLMPort,
    ToolCall,
    ToolSpec,
)

# 长会话上下文裁剪（A3）：LLM 上下文超此消息数 → 只带首条(原始诉求) + 最近若干；
# DB 转录仍全量存，仅裁 LLM 输入控 token/成本。约 20 轮 user+assistant ≈ 40 条。
_CONTEXT_MAX_MESSAGES = 40
_CONTEXT_HEAD = 1


@dataclass(frozen=True)
class ChatEvent:
    """对话流事件（路由序列化为 SSE：event: <type>\\ndata: <json>）。"""

    type: str
    data: dict[str, Any]


def _tool_specs() -> list[ToolSpec]:
    # 工具参数 schema 直接取自请求 DTO（单一事实源，与 launcher 校验同源）。
    # description 强调「信息齐全才调用、缺必填先追问、别把占位问句填进参数」（A3 降残余风险）。
    return [
        ToolSpec(
            "generate",
            "出图（单图流 n 或套图 plan）。仅当已拿到产品图 upload_ids 且比例/张数等必填项"
            "明确时调用；缺任一必填项先用自然语言追问、不要调用。",
            ListingGenerateRequest.model_json_schema(),
        ),
        ToolSpec(
            "clone",
            "爆款图复刻。需产品图 1 张 + 爆款参考图 1..2 张 + clone_mode；未集齐先追问、不要调用。",
            CloneRequest.model_json_schema(),
        ),
        ToolSpec(
            "edit",
            "二次编辑已产出的图。需 source_image_key + 编辑指令；用户未明确要改哪张/怎么改先追问。",
            EditRequest.model_json_schema(),
        ),
    ]


def _title(message: str) -> str:
    text = message.strip().replace("\n", " ")
    return (text[:40] or "新对话")


def _to_llm_messages(transcript: ChatTranscript) -> list[ChatMessage]:
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
    if len(out) <= _CONTEXT_MAX_MESSAGES:
        return out
    elided = ChatMessage(
        role="user", content="[系统备注] 为控制长度，中间若干轮对话已省略，以下为最近对话。"
    )
    return [*out[:_CONTEXT_HEAD], elided, *out[_CONTEXT_HEAD - _CONTEXT_MAX_MESSAGES :]]


@dataclass
class ChatOrchestrator:
    text_llm: TextLLMPort
    launcher: ListingJobLauncher
    event_stream: EventStream
    registry: ProviderRegistry
    chat_repo: ChatSessionRepository
    pending: PendingStore
    max_session_jobs: int = 5  # 会话级出图闸（#884②）
    image_model: ModelName = ModelName.GPT_IMAGE_2
    # 四段 system prompt（persona/知识库/工具契约/守则，A3）：启动组装缓存，可注入便于测试
    system_prompt: str = field(default_factory=default_system_prompt)
    _tools: list[ToolSpec] = field(default_factory=_tool_specs)

    async def handle_message(
        self, user: AuthUser, session_id: str | None, message: str, upload_ids: list[str]
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
        llm_messages = [
            ChatMessage(role="system", content=self.system_prompt),
            *_to_llm_messages(transcript),
        ]

        assistant_text = ""
        tool_calls: tuple[ToolCall, ...] = ()
        try:
            async for chunk in self.text_llm.complete(messages=llm_messages, tools=self._tools):
                if isinstance(chunk, TextChunk):
                    assistant_text += chunk.text
                    yield ChatEvent("assistant_delta", {"text": chunk.text})
                else:
                    tool_calls = chunk.tool_calls
        except TextLLMError as exc:
            yield ChatEvent("error", {"code": "llm_unavailable", "message": str(exc)})
            yield ChatEvent("assistant_end", {"status": "error"})
            return

        if not tool_calls:  # 纯澄清轮：落 assistant 转录，收尾
            await self.chat_repo.append_message(
                session_id=session_id, role="assistant", content=assistant_text
            )
            yield ChatEvent("assistant_end", {"status": "complete"})
            return

        call = tool_calls[0]  # MVP：一轮一工具
        yield ChatEvent("step", {"phase": "planning", "detail": "正在规划出图参数"})
        try:
            req = self._parse_req(call.name, call.arguments)
        except Exception:  # pydantic 校验失败（含 extra=forbid）：内部字段名不吐用户（P3-#5）
            clar = (
                "我还没完全弄清出图要求，麻烦再补充一下"
                "（比如产品、想要的风格和比例），我马上安排。"
            )
            yield ChatEvent("assistant_delta", {"text": clar})
            await self.chat_repo.append_message(
                session_id=session_id, role="assistant", content=clar
            )
            yield ChatEvent("assistant_end", {"status": "complete"})
            return
        try:
            # 与出图同一校验源（#884⑤）：非法参数（占位/缺比例/非自有图）进费用闸前拦下转澄清。
            # validate 的报错文案已是用户话术（无内部字段名，P3-#5），可直接呈现。
            self.launcher.validate(user, req)
        except (ValueError, NotFoundError) as exc:
            clar = f"还差点信息、暂时没法出图：{exc}。你补充一下，我再帮你安排～"
            yield ChatEvent("assistant_delta", {"text": clar})
            await self.chat_repo.append_message(
                session_id=session_id, role="assistant", content=clar
            )
            yield ChatEvent("assistant_end", {"status": "complete"})
            return
        yield ChatEvent("tool_call", {"tool": call.name, "args": call.arguments})

        count = self._count(call.name, req)
        unit_cost = self.registry.get(self.image_model).unit_cost  # 与工作台同源（#884③）
        estimate = unit_cost * count
        pending = self.pending.new(
            session_id, tool=call.name, req=req, count=count, estimate=estimate
        )
        # assistant 最终答复（收尾语+job_id）留到 confirm 后落库；tool_call/cost_confirm 不落库
        yield ChatEvent(
            "cost_confirm",
            {
                "confirm_token": pending.confirm_token,
                "tool": call.name,
                "args": call.arguments,
                "count": count,
                "unit_cost": str(unit_cost),
                "estimate_cny": str(estimate),
            },
        )
        yield ChatEvent("assistant_end", {"status": "awaiting_confirm"})

    async def handle_confirm(
        self, user: AuthUser, session_id: str, confirm_token: str, action: str
    ) -> AsyncIterator[ChatEvent]:
        if not await self.chat_repo.session_owned(session_id, user.user_id):
            yield ChatEvent("error", {"code": "bad_request", "message": "会话不存在或无权访问"})
            yield ChatEvent("assistant_end", {"status": "error"})
            return
        yield ChatEvent("session", {"session_id": session_id})

        if action == "cancel":
            self.pending.clear(session_id)
            yield ChatEvent("assistant_delta", {"text": "已取消本次出图。"})
            await self.chat_repo.append_message(
                session_id=session_id, role="assistant", content="已取消本次出图。"
            )
            yield ChatEvent("assistant_end", {"status": "complete"})
            return
        if action != "confirm":
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
        except (ValueError, NotFoundError, RateLimited, BudgetExceeded) as exc:
            yield ChatEvent("error", {"code": self._err_code(exc), "message": str(exc)})
            yield ChatEvent("assistant_end", {"status": "error"})
            return
        plan = pending.req.plan if isinstance(pending.req, ListingGenerateRequest) else None
        yield ChatEvent(
            "job_started",
            {"job_id": job_id, "tool": pending.tool, "count": pending.count, "plan": plan},
        )

        completed = False
        async for event in self.event_stream.subscribe(job_id):
            yield ChatEvent(
                "job_event", {"job_id": job_id, "type": event.type.value, "data": event.data}
            )
            if event.type == TaskEventType.TASK_COMPLETED:
                completed = True

        # 收尾轮：从 DB 转录重建上下文 + 系统提示出图结果 → LLM 产自然收尾语（无工具）
        summary = "出图完成" if completed else "出图失败或部分失败"
        transcript = await self.chat_repo.get_transcript(session_id, user.user_id)
        note = ChatMessage(
            role="user",
            content=f"（系统提示）刚才的出图已{summary}，请用一句自然的话向用户收尾，不要再调用工具。",
        )
        history = _to_llm_messages(transcript) if transcript is not None else []
        llm_messages = [ChatMessage(role="system", content=self.system_prompt), *history, note]
        closing = ""
        try:
            async for chunk in self.text_llm.complete(messages=llm_messages, tools=[]):
                if isinstance(chunk, TextChunk):
                    closing += chunk.text
                    yield ChatEvent("assistant_delta", {"text": chunk.text})
        except TextLLMError:
            closing = "已完成，可在结果区查看。" if completed else "很抱歉，出图未成功，请重试。"
            yield ChatEvent("assistant_delta", {"text": closing})
        # 落 assistant 最终答复（+job_id，回显时 job_id→image_key→现签图，取舍②）
        await self.chat_repo.append_message(
            session_id=session_id, role="assistant", content=closing, job_id=job_id
        )
        yield ChatEvent("assistant_end", {"status": "complete"})

    async def _launch(self, user: AuthUser, pending: PendingAction) -> str:
        req = pending.req
        if pending.tool == "generate" and isinstance(req, ListingGenerateRequest):
            return await self.launcher.launch_generate(user, req)
        if pending.tool == "clone" and isinstance(req, CloneRequest):
            return await self.launcher.launch_clone(user, req)
        if pending.tool == "edit" and isinstance(req, EditRequest):
            return await self.launcher.launch_edit(user, req)
        raise ValueError(f"未知工具：{pending.tool}")

    @staticmethod
    def _parse_req(
        tool: str, args: dict[str, Any]
    ) -> ListingGenerateRequest | CloneRequest | EditRequest:
        if tool == "generate":
            return ListingGenerateRequest(**args)
        if tool == "clone":
            return CloneRequest(**args)
        if tool == "edit":
            return EditRequest(**args)
        raise ValueError(f"未知工具：{tool}")

    @staticmethod
    def _count(
        tool: str, req: ListingGenerateRequest | CloneRequest | EditRequest
    ) -> int:
        if tool == "generate" and isinstance(req, ListingGenerateRequest):
            if req.n is not None:
                return req.n
            if req.plan is not None:
                return sum(req.plan.values())
        return 1

    @staticmethod
    def _err_code(exc: Exception) -> str:
        if isinstance(exc, RateLimited):
            return "rate_limited"
        if isinstance(exc, BudgetExceeded):
            return "budget_exceeded"
        return "bad_request"  # ValueError / NotFoundError
