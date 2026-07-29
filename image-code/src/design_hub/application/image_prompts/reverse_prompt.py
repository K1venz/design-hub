from collections.abc import AsyncIterator
from dataclasses import dataclass
from io import BytesIO
from typing import Annotated

from PIL import Image, UnidentifiedImageError
from pydantic import (
    BaseModel,
    ConfigDict,
    StringConstraints,
    ValidationError,
)

from design_hub.application.listing.requests import ImageSource
from design_hub.application.listing.upload_service import UploadService
from design_hub.domain.errors import NotFoundError
from design_hub.ports.image_store import ImageStore
from design_hub.ports.listing_query import ListingHistoryQuery
from design_hub.ports.text_llm import (
    ChatImage,
    ChatMessage,
    LLMChunk,
    TextLLMError,
    TextLLMPort,
    ToolCall,
    ToolCallChunk,
    ToolSpec,
)
from design_hub.ports.upload_store import owns

_RESULT_TOOL = "return_reverse_prompt"
_MEDIA_TYPES = {
    "PNG": "image/png",
    "JPEG": "image/jpeg",
    "WEBP": "image/webp",
}
_SYSTEM_PROMPT = """分析用户提供的真实图片，并调用 return_reverse_prompt 返回结构化结果。
只描述画面中可观察或可合理推断的内容；不确定的信息必须写入 uncertainties。
不要声称恢复了原作者的真实提示词。prompt_zh 和 prompt_en 是用于重建画面的建议。"""

NonEmptyText = Annotated[
    str,
    StringConstraints(strip_whitespace=True, min_length=1),
]


class ReversePromptRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    source: ImageSource


class ReversePromptResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    summary: NonEmptyText
    subject: NonEmptyText
    scene: NonEmptyText
    composition: NonEmptyText
    camera: NonEmptyText
    lighting: NonEmptyText
    colors: list[NonEmptyText]
    style: NonEmptyText
    visible_text: list[NonEmptyText]
    constraints: list[NonEmptyText]
    uncertainties: list[NonEmptyText]
    prompt_zh: NonEmptyText
    prompt_en: NonEmptyText


@dataclass(frozen=True)
class ReversePromptService:
    text_llm: TextLLMPort
    uploads: UploadService
    images: ImageStore
    query: ListingHistoryQuery

    async def reverse(
        self,
        *,
        user_id: str,
        request: ReversePromptRequest,
    ) -> ReversePromptResult:
        image_data = await self._load_image(user_id=user_id, request=request)
        media_type = _detect_media_type(image_data)
        messages = [
            ChatMessage(role="system", content=_SYSTEM_PROMPT),
            ChatMessage(
                role="user",
                content="请分析这张图片并返回完整的结构化反推提示词。",
                images=(ChatImage(data=image_data, media_type=media_type),),
            ),
        ]
        tool = ToolSpec(
            name=_RESULT_TOOL,
            description="返回图片分析和中英文重建提示词",
            parameters=ReversePromptResult.model_json_schema(),
            required=True,
        )
        calls = await _collect_tool_calls(
            self.text_llm.complete(messages=messages, tools=[tool])
        )
        if len(calls) != 1 or calls[0].name != _RESULT_TOOL:
            raise TextLLMError("反推提示词模型未返回唯一的结构化结果")
        try:
            return ReversePromptResult.model_validate(calls[0].arguments)
        except ValidationError as exc:
            raise TextLLMError("反推提示词模型返回结构不完整") from exc

    async def _load_image(
        self,
        *,
        user_id: str,
        request: ReversePromptRequest,
    ) -> bytes:
        if request.source.kind == "upload":
            if not owns(request.source.upload_id, user_id):
                raise NotFoundError("图片不存在或无权访问，请重新选择后再试")
            data, _content_type = await self.uploads.load(
                request.source.upload_id
            )
            return data

        source = await self.query.resolve_generated_image_source(
            source_image_key=request.source.image_key,
            user_id=user_id,
        )
        if source is None:
            raise NotFoundError("图片不存在或无权访问，请重新选择后再试")
        return await self.images.load(request.source.image_key)


def format_reverse_prompt(result: ReversePromptResult) -> str:
    visible_text = "、".join(result.visible_text) or "未识别到明确文字"
    constraints = "\n".join(f"- {item}" for item in result.constraints) or "- 无"
    uncertainties = (
        "\n".join(f"- {item}" for item in result.uncertainties)
        or "- 无"
    )
    colors = "、".join(result.colors) or "未提取"
    return (
        f"画面概述：{result.summary}\n"
        f"主体：{result.subject}\n"
        f"场景：{result.scene}\n"
        f"构图：{result.composition}\n"
        f"镜头：{result.camera}\n"
        f"光线：{result.lighting}\n"
        f"色彩：{colors}\n"
        f"风格：{result.style}\n"
        f"可见文字：{visible_text}\n\n"
        f"重建约束：\n{constraints}\n\n"
        f"不确定项：\n{uncertainties}\n\n"
        f"中文提示词：\n{result.prompt_zh}\n\n"
        f"English prompt:\n{result.prompt_en}"
    )


async def _collect_tool_calls(
    chunks: AsyncIterator[LLMChunk],
) -> tuple[ToolCall, ...]:
    calls: list[ToolCall] = []
    async for chunk in chunks:
        if isinstance(chunk, ToolCallChunk):
            calls.extend(chunk.tool_calls)
    return tuple(calls)


def _detect_media_type(data: bytes) -> str:
    try:
        with Image.open(BytesIO(data)) as image:
            image_format = image.format
            image.verify()
    except (UnidentifiedImageError, OSError, ValueError) as exc:
        raise ValueError("图片损坏或无法读取，请重新上传") from exc
    media_type = _MEDIA_TYPES.get(image_format or "")
    if media_type is None:
        raise ValueError("图片格式不受支持，请上传 PNG、JPEG 或 WebP")
    return media_type
