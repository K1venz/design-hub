"""ChatOrchestrator（方案 C 零框架 tool-use 循环 + 对话历史持久化 ISSUE-0051）。

多轮澄清 → LLM 产结构化 tool_call（= /listing 请求体字段，绝不直出图像 prompt，铁律①）
→ 费用确认闸（暂停）→ 用户确认 → 经 ListingJobLauncher 走同一出图链（频控/owner/
成本守卫/卡链全继承，#884⑤）→ 转发 job SSE（包一层 job_event）→ 收尾话术。

转录持久化（取舍①）：user 消息 + assistant 最终答复(+job_id) 落 ChatSessionRepository；
过程态（流式吐字/步骤/费用卡/tool_call）不落库。LLM 多轮上下文每轮从 DB 转录重建（刷新/
重启可续）。confirm_token 留内存（PendingStore，取舍⑤）。产出 ChatEvent 流由 /chat 路由序列化 SSE。
"""

import uuid
from collections import Counter
from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from typing import Any

from design_hub.application.chat.image_ratio import detect_supported_ratio
from design_hub.application.chat.pending_store import PendingAction, PendingStore
from design_hub.application.chat.system_prompt import default_system_prompt
from design_hub.application.chat.tool_requests import ChatCloneRequest, ChatGenerateRequest
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
from design_hub.ports.ledger import LedgerRepository
from design_hub.ports.listing_query import ListingHistoryQuery
from design_hub.ports.model_config_repository import ModelConfigRepository
from design_hub.ports.text_llm import (
    ChatMessage,
    TextChunk,
    TextLLMError,
    TextLLMPort,
    ToolCall,
    ToolSpec,
)
from design_hub.ports.upload_store import UploadReadError, owns

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
_WRITE_TOOLS = frozenset({"generate", "clone", "edit"})
_READ_TOOLS = frozenset({"query_my_jobs", "get_job_recipe", "get_pricing_quota"})
_MAX_TOOL_ITERS = 5  # 读工具回喂循环上限（防 LLM 无限调工具）


def _tool_specs() -> list[ToolSpec]:
    # 工具参数 schema 直接取自请求 DTO（单一事实源，与 launcher 校验同源）。
    # description 强调「信息齐全才调用、缺必填先追问、别把占位问句填进参数」（A3 降残余风险）。
    return [
        ToolSpec(
            "generate",
            "出图（单图流 n 或套图 plan）。拿到产品图 upload_ids 且用户意图可执行时调用；"
            "比例由系统备注提供，用户文字明确指定时覆盖。未明确套图或张数时按单图 n=1，"
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
            EditRequest.model_json_schema(),
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
        ToolSpec(
            "get_pricing_quota",
            "查价格与当前用户额度（真实数据）。用户问「多少钱/我还能出几张/额度」时用。",
            {"type": "object", "properties": {}},
        ),
    ]


def _title(message: str) -> str:
    text = message.strip().replace("\n", " ")
    return (text[:40] or "新对话")


def _to_llm_messages(
    transcript: ChatTranscript, *, current_auto_ratio: str | None = None
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
    if current_auto_ratio is not None:
        if not out or out[-1].role != "user":
            raise ValueError("自动比例只能注入当前 user 消息")
        current = out[-1]
        ratio_note = (
            f"[系统备注] 本轮自动比例={current_auto_ratio}。"
            "用户文字明确指定比例时以文字为准；否则使用自动比例，不要追问比例。"
        )
        out[-1] = ChatMessage(
            role=current.role,
            content=f"{current.content}\n\n{ratio_note}",
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
    text_llm: TextLLMPort
    launcher: ListingJobLauncher
    event_stream: EventStream
    registry: ProviderRegistry
    chat_repo: ChatSessionRepository
    pending: PendingStore
    query: ListingHistoryQuery  # 读工具：出图历史/配方（owner-scoped，护栏③）
    ledger: LedgerRepository  # 读工具：额度真数据
    model_config: ModelConfigRepository  # 读工具：价格/启用模型实时值（波动信息走工具，#1043）
    max_session_jobs: int = 5  # 会话级出图闸（#884②）
    image_model: ModelName = ModelName.GPT_IMAGE_2
    # 四段 system prompt（persona/知识库/工具契约/守则，A3）：启动组装缓存，可注入便于测试
    system_prompt: str = field(default_factory=default_system_prompt)
    _tools: list[ToolSpec] = field(default_factory=_tool_specs)

    async def _auto_ratio(self, user: AuthUser, upload_ids: list[str]) -> str:
        if not upload_ids or not owns(upload_ids[0], user.user_id):
            return "1:1"
        try:
            data, _content_type = await self.launcher.uploads.load(upload_ids[0])
        except (ValueError, NotFoundError, UploadReadError):
            return "1:1"
        return detect_supported_ratio(data)

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
        auto_ratio = await self._auto_ratio(user, upload_ids)
        llm_messages = [
            ChatMessage(role="system", content=self.system_prompt),
            *_to_llm_messages(transcript, current_auto_ratio=auto_ratio),
        ]

        # 工具化 tool-use 循环（A3）：读工具即时执行→结果回喂→再问 LLM；写工具→费用闸；纯文本→收尾。
        for _ in range(_MAX_TOOL_ITERS):
            assistant_text = ""
            tool_calls: tuple[ToolCall, ...] = ()
            try:
                async for chunk in self.text_llm.complete(
                    messages=llm_messages, tools=self._tools
                ):
                    if isinstance(chunk, TextChunk):
                        assistant_text += chunk.text
                        yield ChatEvent("assistant_delta", {"text": chunk.text})
                    else:
                        tool_calls = chunk.tool_calls
            except TextLLMError as exc:
                yield ChatEvent("error", {"code": "llm_unavailable", "message": str(exc)})
                yield ChatEvent("assistant_end", {"status": "error"})
                return

            if not tool_calls:  # 纯文本（澄清/答复/顾问建议）：落 assistant 转录，收尾
                await self.chat_repo.append_message(
                    session_id=session_id, role="assistant", content=assistant_text
                )
                yield ChatEvent("assistant_end", {"status": "complete"})
                return

            call = tool_calls[0]  # MVP：一轮一工具
            if call.name in _READ_TOOLS:  # 读工具：owner-scoped 即时执行回喂（护栏③；不落库）
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
                # 与出图同一校验源（#884⑤/护栏②）：非法参数进费用闸前拦下转澄清；文案已是用户话术。
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

    # ── 读工具（A3 工具化，owner-scoped 护栏③；不花钱、不过费用闸；结果回喂 LLM）──

    async def _run_read_tool(self, user: AuthUser, call: ToolCall) -> str:
        """派发读工具→文本结果（回喂 LLM）。异常兜底为文本，保持对话不中断（I/O 域）。"""
        try:
            if call.name == "query_my_jobs":
                return await self._tool_query_my_jobs(user, call.arguments)
            if call.name == "get_job_recipe":
                return await self._tool_get_job_recipe(user, call.arguments)
            if call.name == "get_pricing_quota":
                return await self._tool_get_pricing_quota(user)
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
            "要用这套配置再出一套，就用这些参数调 generate（仍会先报预计费用等用户确认）。"
        )

    async def _tool_get_pricing_quota(self, user: AuthUser) -> str:
        # 波动值走实时查（#1043）：价格/启用模型读 model_config 表当前值——管理员改价即变，
        # 绝不背知识库写死数字。0057 上线后多模型/渠道自动进这份清单。
        configs = await self.model_config.list_all()
        enabled = [c for c in configs if c.enabled]
        current = next((c for c in configs if c.name == self.image_model.value), None)
        unit_cost = current.unit_cost if current else self.registry.get(self.image_model).unit_cost
        snap = await self.ledger.snapshot(user.user_id)
        remaining = snap.user_monthly_quota - snap.user_month_used
        approx = int(remaining / unit_cost) if unit_cost else 0
        models = "、".join(f"{c.name}(¥{c.unit_cost}/张)" for c in enabled) or "（暂无启用模型）"
        return (
            f"价格（管理员实时配置）：当前出图约 ¥{unit_cost}/张。\n"
            f"当前启用模型：{models}。\n"
            f"该用户额度：已用 ¥{snap.user_month_used} / 额度 ¥{snap.user_monthly_quota}，"
            f"剩余约 ¥{remaining}（≈ {approx} 张）。\n当前内测期间，未开放公开充值。"
        )

    @staticmethod
    def _parse_req(
        tool: str, args: dict[str, Any]
    ) -> ListingGenerateRequest | CloneRequest | EditRequest:
        if tool == "generate":
            return ChatGenerateRequest(**args).to_listing()
        if tool == "clone":
            return ChatCloneRequest(**args).to_listing()
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
